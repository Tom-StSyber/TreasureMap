#!/usr/bin/env bash
# ── TreasureMap — native Ubuntu 24.04 installer (no Docker required) ──────────
#
# Run via the root Install-TreasureMap.sh — do not call directly unless you
# know what you are doing.
#
# What this script does:
#   1. Installs system packages (Python 3.12, Node 20, curl, unzip)
#   2. Downloads and extracts Elasticsearch 8.13.0 into ./elasticsearch/server/
#   3. Creates the Python virtual environment and installs pip deps
#   4. Installs npm packages for the frontend
#   5. Starts Elasticsearch, waits for it to be healthy
#   6. Ingests the synthetic lab dataset via the API stream endpoint
#   7. Prints start instructions

set -euo pipefail
IFS=$'\n\t'

# ── Resolve project root ──────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$ROOT"

# ── Colour helpers ────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; MAGENTA='\033[0;35m'; NC='\033[0m'
info()  { echo -e "${CYAN}  [INFO]  $*${NC}"; }
ok()    { echo -e "${GREEN}  [ OK ]  $*${NC}"; }
warn()  { echo -e "${YELLOW}  [WARN]  $*${NC}"; }
die()   { echo -e "${RED}  [FAIL]  $*${NC}"; exit 1; }
head()  { echo -e "\n${MAGENTA}══ $* ══${NC}"; }

# ── Banner ────────────────────────────────────────────────────────────────────
echo -e "${CYAN}"
cat << 'BANNER'
  ████████╗██████╗ ███████╗ █████╗ ███████╗██╗   ██╗██████╗ ███████╗███╗   ███╗ █████╗ ██████╗
     ██╔══╝██╔══██╗██╔════╝██╔══██╗██╔════╝██║   ██║██╔══██╗██╔════╝████╗ ████║██╔══██╗██╔══██╗
     ██║   ██████╔╝█████╗  ███████║███████╗██║   ██║██████╔╝█████╗  ██╔████╔██║███████║██████╔╝
     ██║   ██╔══██╗██╔══╝  ██╔══██║╚════██║██║   ██║██╔══██╗██╔══╝  ██║╚██╔╝██║██╔══██║██╔═══╝
     ██║   ██║  ██║███████╗██║  ██║███████║╚██████╔╝██║  ██║███████╗██║ ╚═╝ ██║██║  ██║██║
     ╚═╝   ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚══════╝╚═╝     ╚═╝╚═╝  ╚═╝╚═╝

  Network Topology Visualiser — Ubuntu Native Installer
BANNER
echo -e "${NC}  Project root: $ROOT\n"

# ── Constants ─────────────────────────────────────────────────────────────────
ES_VERSION="8.13.0"
ES_URL="https://artifacts.elastic.co/downloads/elasticsearch/elasticsearch-${ES_VERSION}-linux-x86_64.tar.gz"
ES_DIR="$ROOT/elasticsearch/server/elasticsearch-${ES_VERSION}"
ES_DATA="$ROOT/elasticsearch/data"
ES_LOGS="$ROOT/elasticsearch/logs"
ES_TARBALL="$ROOT/elasticsearch/elasticsearch-${ES_VERSION}-linux-x86_64.tar.gz"
VENV="$ROOT/backend/.venv"

# ─────────────────────────────────────────────────────────────────────────────
head "Step 1 — System packages"
# ─────────────────────────────────────────────────────────────────────────────

NEED_SUDO=""
if [[ $EUID -ne 0 ]]; then
    NEED_SUDO="sudo"
    warn "Not running as root — using sudo for apt commands."
fi

info "Updating apt cache…"
$NEED_SUDO apt-get update -qq

# Python 3.12
if ! command -v python3.12 &>/dev/null; then
    info "Installing Python 3.12…"
    $NEED_SUDO apt-get install -y -qq python3.12 python3.12-venv python3-pip
fi
ok "Python: $(python3.12 --version)"

# Node.js 20 LTS via NodeSource
if ! command -v node &>/dev/null || [[ $(node --version | grep -oP '(?<=v)\d+') -lt 20 ]]; then
    info "Installing Node.js 20 LTS via NodeSource…"
    $NEED_SUDO apt-get install -y -qq curl
    curl -fsSL https://deb.nodesource.com/setup_20.x | $NEED_SUDO bash - >/dev/null 2>&1
    $NEED_SUDO apt-get install -y -qq nodejs
fi
ok "Node.js: $(node --version)  |  npm: $(npm --version)"

# Utilities
$NEED_SUDO apt-get install -y -qq curl wget unzip tar jq >/dev/null 2>&1
ok "Utilities installed (curl wget unzip tar jq)"

# ─────────────────────────────────────────────────────────────────────────────
head "Step 2 — Elasticsearch $ES_VERSION"
# ─────────────────────────────────────────────────────────────────────────────

# Elasticsearch must not run as root
if [[ $EUID -eq 0 ]]; then
    die "Elasticsearch cannot run as root. Please re-run this script as a regular user (with sudo available)."
fi

mkdir -p "$ROOT/elasticsearch/server" "$ES_DATA" "$ES_LOGS"

if [[ ! -f "$ES_DIR/bin/elasticsearch" ]]; then
    if [[ ! -f "$ES_TARBALL" ]]; then
        info "Downloading Elasticsearch $ES_VERSION (~330 MB)…"
        wget -q --show-progress -O "$ES_TARBALL" "$ES_URL"
    fi
    info "Extracting…"
    tar -xzf "$ES_TARBALL" -C "$ROOT/elasticsearch/server/"
    rm -f "$ES_TARBALL"
    ok "Elasticsearch extracted to $ES_DIR"
else
    ok "Elasticsearch already present"
fi

# Write elasticsearch.yml with resolved paths
sed \
    -e "s|__ES_DATA_PATH__|${ES_DATA}|g" \
    -e "s|__ES_LOGS_PATH__|${ES_LOGS}|g" \
    "$ROOT/elasticsearch/config/elasticsearch.yml" \
    > "$ES_DIR/config/elasticsearch.yml"
ok "elasticsearch.yml written"

# ─────────────────────────────────────────────────────────────────────────────
head "Step 3 — Backend Python environment"
# ─────────────────────────────────────────────────────────────────────────────

if [[ ! -f "$VENV/bin/python" ]]; then
    info "Creating virtual environment…"
    python3.12 -m venv "$VENV"
fi
ok "Virtual environment: $VENV"

info "Installing Python dependencies…"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -r "$ROOT/backend/requirements.txt"
ok "Python dependencies installed"

# Create .env if missing
if [[ ! -f "$ROOT/backend/.env" ]]; then
    cp "$ROOT/.env.example" "$ROOT/backend/.env"
    ok ".env created from template"
else
    ok ".env already exists — not overwritten"
fi

# ─────────────────────────────────────────────────────────────────────────────
head "Step 4 — Frontend npm packages"
# ─────────────────────────────────────────────────────────────────────────────

(cd "$ROOT/frontend" && npm install --silent)
ok "npm packages installed"

# ─────────────────────────────────────────────────────────────────────────────
head "Step 5 — Start Elasticsearch"
# ─────────────────────────────────────────────────────────────────────────────

if curl -sf http://localhost:9200 >/dev/null 2>&1; then
    ok "Elasticsearch already running"
else
    info "Starting Elasticsearch (first boot may take 30-60 s)…"
    export ES_JAVA_OPTS="-Xms1g -Xmx1g"
    nohup "$ES_DIR/bin/elasticsearch" > "$ES_LOGS/install-start.log" 2>&1 &
    ES_PID=$!
    echo $ES_PID > "$ROOT/elasticsearch/es.pid"

    TIMEOUT=120; ELAPSED=0
    while [[ $ELAPSED -lt $TIMEOUT ]]; do
        sleep 5; ELAPSED=$((ELAPSED+5))
        STATUS=$(curl -sf http://localhost:9200/_cluster/health 2>/dev/null | jq -r '.status' 2>/dev/null || echo "")
        [[ "$STATUS" == "green" || "$STATUS" == "yellow" ]] && break
        printf "."
    done
    echo ""
    [[ $ELAPSED -ge $TIMEOUT ]] && die "Elasticsearch did not start within ${TIMEOUT}s. Check $ES_LOGS/install-start.log"
    ok "Elasticsearch healthy"
fi

# ─────────────────────────────────────────────────────────────────────────────
head "Step 6 — Ingest synthetic lab data"
# ─────────────────────────────────────────────────────────────────────────────

info "Starting API server briefly for ingest…"
(cd "$ROOT/backend" && "$VENV/bin/uvicorn" main:app --host 127.0.0.1 --port 8000 > /tmp/tm-api-install.log 2>&1) &
API_PID=$!
sleep 6

LAB_DIR="$ROOT/data/synthetic-lab"
info "Ingesting configs from $LAB_DIR …"
INGEST_RESP=$(curl -sf "http://localhost:8000/ingest/stream?folder_path=${LAB_DIR}&wipe=true" 2>/dev/null || echo "FAILED")

if echo "$INGEST_RESP" | grep -q '"type": "done"'; then
    SUMMARY=$(echo "$INGEST_RESP" | grep '"type": "done"' | python3 -c "import sys,json; d=json.loads(sys.stdin.read().split('data: ')[1]); s=d['summary']; print(f\"devices={s['devices']} connections={s['connections']} acls={s['acls']}\")" 2>/dev/null || echo "")
    ok "Ingest complete — $SUMMARY"
else
    warn "Ingest returned unexpected output. Re-run ingest from the UI after starting."
fi

kill $API_PID 2>/dev/null || true
wait $API_PID 2>/dev/null || true

# ─────────────────────────────────────────────────────────────────────────────
head "Installation complete!"
# ─────────────────────────────────────────────────────────────────────────────
echo -e "${GREEN}"
cat << 'DONE'
  Everything is installed. To start TreasureMap:

    ./Start-TreasureMap.sh       (from the project root)
    — or manually —
    Backend:  cd backend && ../.venv/bin/uvicorn main:app --reload
    Frontend: cd frontend && npm run dev

  URLs:
    UI       →  http://localhost:5173
    API docs →  http://localhost:8000/docs

DONE
echo -e "${NC}"

read -rp "  Start TreasureMap now? [Y/n] " START
if [[ "$START" != "n" && "$START" != "N" ]]; then
    exec "$ROOT/scripts/ubuntu/start-native.sh"
fi
