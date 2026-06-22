#!/usr/bin/env bash
# =============================================================================
# TreasureMap — Full Bootstrap Installer for Ubuntu 24.04 LTS
# =============================================================================
# Usage (as a non-root user with sudo rights):
#   chmod +x Install-TreasureMap.sh
#   ./Install-TreasureMap.sh
#
# What this script installs:
#   - System prerequisites (curl, git, ca-certificates, gnupg, lsb-release)
#   - Docker Engine + Docker Compose plugin (official Docker apt repo)
#   - Node.js 20 LTS (official NodeSource apt repo)
#   - Python 3.12 + pip (Ubuntu 24.04 default — already present)
#   - TreasureMap application (cloned from GitHub if not already present)
#   - All npm dependencies (pinned, in frontend/)
#   - All Python dependencies (in a venv under backend/)
#   - Docker services: Elasticsearch 8.13, Kibana 8.13, FastAPI backend, nginx frontend
#
# After this script completes, TreasureMap runs entirely in Docker containers.
# Node and Python on the host are only needed for dev-mode hot-reload.
#
# Golden VM workflow:
#   1. Run this script once on a clean Ubuntu 24.04 VM with internet access.
#   2. Verify TreasureMap is healthy (see end-of-script output).
#   3. Shut down the VM and clone it for each analyst.
#   4. Each clone only needs to start the VM — no internet required.
# =============================================================================
set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────────────────
REPO_URL="https://github.com/Tom-StSyber/TreasureMap.git"
INSTALL_DIR="${HOME}/TreasureMap"
NODE_MAJOR=20

# Override with environment variables if needed, e.g.:
#   REPO_URL=https://github.com/acme/TreasureMap.git ./Install-TreasureMap.sh
# =============================================================================

BOLD="\033[1m"
GREEN="\033[1;32m"
YELLOW="\033[1;33m"
RED="\033[1;31m"
RESET="\033[0m"

info()    { echo -e "${GREEN}[✓]${RESET} $*"; }
warn()    { echo -e "${YELLOW}[!]${RESET} $*"; }
section() { echo -e "\n${BOLD}══ $* ══${RESET}"; }
die()     { echo -e "${RED}[✗] ERROR:${RESET} $*" >&2; exit 1; }

# ── Preflight ─────────────────────────────────────────────────────────────────
section "Preflight checks"

[[ "$(id -u)" -eq 0 ]] && die "Do NOT run this script as root. Run as a normal user with sudo rights."

# Confirm Ubuntu 24.04
if ! grep -qi "ubuntu" /etc/os-release 2>/dev/null; then
    warn "This installer targets Ubuntu 24.04. Proceeding anyway, but results may vary."
fi

# Verify sudo works
sudo -v || die "sudo not available or password rejected."
info "Running as $(whoami) with sudo access."

# ── System prerequisites ───────────────────────────────────────────────────────
section "Installing system prerequisites"

sudo apt-get update -qq
sudo apt-get install -y -qq \
    ca-certificates \
    curl \
    git \
    gnupg \
    lsb-release \
    python3 \
    python3-pip \
    python3-venv \
    2>/dev/null

info "System prerequisites installed."

# ── Docker Engine ──────────────────────────────────────────────────────────────
section "Installing Docker Engine"

if command -v docker &>/dev/null && docker compose version &>/dev/null; then
    info "Docker $(docker --version | awk '{print $3}' | tr -d ',') already installed — skipping."
else
    # Remove any old/conflicting packages
    for pkg in docker.io docker-doc docker-compose docker-compose-v2 podman-docker containerd runc; do
        sudo apt-get remove -y -qq "$pkg" 2>/dev/null || true
    done

    # Add Docker's official GPG key
    sudo install -m 0755 -d /etc/apt/keyrings
    sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
        -o /etc/apt/keyrings/docker.asc
    sudo chmod a+r /etc/apt/keyrings/docker.asc

    # Add Docker apt repository
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
      https://download.docker.com/linux/ubuntu \
      $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
      sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

    sudo apt-get update -qq
    sudo apt-get install -y -qq \
        docker-ce \
        docker-ce-cli \
        containerd.io \
        docker-buildx-plugin \
        docker-compose-plugin \
        2>/dev/null

    info "Docker $(docker --version | awk '{print $3}' | tr -d ',') installed."
fi

# Allow current user to run Docker without sudo
if ! groups | grep -q docker; then
    sudo usermod -aG docker "$USER"
    warn "Added $USER to the docker group. This takes effect in a new shell session."
    warn "The script will use 'sudo docker' for the remainder of this run."
    DOCKER_CMD="sudo docker"
else
    DOCKER_CMD="docker"
fi

# ── Node.js 20 LTS ────────────────────────────────────────────────────────────
section "Installing Node.js ${NODE_MAJOR} LTS"

INSTALLED_NODE_MAJOR=0
if command -v node &>/dev/null; then
    INSTALLED_NODE_MAJOR=$(node --version | sed 's/v\([0-9]*\).*/\1/')
fi

if [[ "$INSTALLED_NODE_MAJOR" -ge "$NODE_MAJOR" ]]; then
    info "Node.js $(node --version) already installed — skipping."
else
    if [[ "$INSTALLED_NODE_MAJOR" -gt 0 ]]; then
        warn "Node.js $(node --version) is installed but too old (need $NODE_MAJOR+). Replacing via NodeSource."
        # Remove system nodejs so NodeSource version takes priority
        sudo apt-get remove -y -qq nodejs npm 2>/dev/null || true
    fi

    # NodeSource official setup script
    curl -fsSL https://deb.nodesource.com/setup_${NODE_MAJOR}.x | sudo -E bash - 2>/dev/null
    sudo apt-get install -y -qq nodejs 2>/dev/null
    info "Node.js $(node --version) / npm $(npm --version) installed."
fi

# ── Clone or update TreasureMap ───────────────────────────────────────────────
section "Setting up TreasureMap repository"

if [[ -d "$INSTALL_DIR/.git" ]]; then
    info "Repository already exists at $INSTALL_DIR — pulling latest."
    git -C "$INSTALL_DIR" pull --ff-only
else
    info "Cloning TreasureMap into $INSTALL_DIR …"
    git clone "$REPO_URL" "$INSTALL_DIR"
fi

cd "$INSTALL_DIR"
info "Working directory: $(pwd)"

# ── npm install (frontend) ────────────────────────────────────────────────────
section "Installing frontend npm dependencies"

# IMPORTANT: npm commands MUST run from the frontend/ subdirectory.
# package.json is at frontend/package.json — there is NO root-level package.json.
cd "$INSTALL_DIR/frontend"

# Always delete any existing lockfile and regenerate from the pinned package.json.
# This prevents stale lockfile conflicts when package versions have been updated.
rm -f package-lock.json
npm install
info "npm install completed (dependencies pinned to exact versions in package.json)."

cd "$INSTALL_DIR"

# ── Python venv (backend — host-side dev tools only) ─────────────────────────
section "Setting up Python virtual environment (backend)"

# The backend runs in Docker in production, but a local venv lets analysts
# run ingest.py and other scripts directly during development.
if [[ ! -d "$INSTALL_DIR/backend/.venv" ]]; then
    python3 -m venv "$INSTALL_DIR/backend/.venv"
    info "Created virtualenv at backend/.venv"
fi

source "$INSTALL_DIR/backend/.venv/bin/activate"
pip install --quiet --upgrade pip
pip install --quiet -r "$INSTALL_DIR/backend/requirements.txt"
deactivate
info "Python dependencies installed into backend/.venv"

# ── Docker services ───────────────────────────────────────────────────────────
section "Starting Docker services"

# Pull images first so the startup output is cleaner
$DOCKER_CMD compose pull --quiet 2>/dev/null || true

$DOCKER_CMD compose up -d --build
info "Containers started. Waiting for Elasticsearch to become healthy…"

# ── Wait for Elasticsearch ────────────────────────────────────────────────────
ES_URL="http://localhost:9200/_cluster/health"
MAX_WAIT=120   # seconds
ELAPSED=0

while true; do
    STATUS=$(curl -sf "$ES_URL" 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','red'))" 2>/dev/null || echo "red")
    if [[ "$STATUS" == "green" || "$STATUS" == "yellow" ]]; then
        info "Elasticsearch is healthy (status: $STATUS)."
        break
    fi
    if [[ "$ELAPSED" -ge "$MAX_WAIT" ]]; then
        die "Elasticsearch did not become healthy within ${MAX_WAIT}s. Check: $DOCKER_CMD compose logs elasticsearch"
    fi
    printf "  waiting… (%ds)\r" "$ELAPSED"
    sleep 5
    ELAPSED=$((ELAPSED + 5))
done

# ── Seed sample data ──────────────────────────────────────────────────────────
section "Seeding sample network data"

# Run ingest inside the api container so it uses the container's network and ES endpoint
if $DOCKER_CMD compose exec -T api python3 ingest.py; then
    info "Sample data ingested successfully."
else
    warn "ingest.py returned a non-zero exit code. This is not fatal — you can re-run it later:"
    warn "  cd $INSTALL_DIR && $DOCKER_CMD compose exec api python3 ingest.py"
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}══════════════════════════════════════════════════"
echo -e "  TreasureMap installation complete!"
echo -e "══════════════════════════════════════════════════${RESET}"
echo ""
echo -e "  ${BOLD}UI:${RESET}       http://localhost:3000"
echo -e "  ${BOLD}API docs:${RESET} http://localhost:8000/docs"
echo -e "  ${BOLD}Kibana:${RESET}   http://localhost:5601"
echo ""
echo -e "  ${BOLD}Service management:${RESET}"
echo -e "    Start:   cd $INSTALL_DIR && $DOCKER_CMD compose up -d"
echo -e "    Stop:    cd $INSTALL_DIR && $DOCKER_CMD compose down"
echo -e "    Logs:    cd $INSTALL_DIR && $DOCKER_CMD compose logs -f"
echo -e "    Restart: cd $INSTALL_DIR && $DOCKER_CMD compose restart"
echo ""
echo -e "  ${BOLD}Dev mode (hot-reload, outside Docker):${RESET}"
echo -e "    Frontend: cd $INSTALL_DIR/frontend && npm run dev"
echo -e "    Backend:  cd $INSTALL_DIR/backend && source .venv/bin/activate && uvicorn main:app --reload"
echo ""
if ! groups | grep -q docker; then
    echo -e "  ${YELLOW}${BOLD}ACTION REQUIRED:${RESET} Log out and back in (or run 'newgrp docker')"
    echo -e "  so your user can run Docker commands without sudo."
    echo ""
fi
