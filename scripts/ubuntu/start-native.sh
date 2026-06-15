#!/usr/bin/env bash
# ── TreasureMap — start all native services (Ubuntu) ─────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

GREEN='\033[0;32m'; CYAN='\033[0;36m'; RED='\033[0;31m'; NC='\033[0m'
ok()  { echo -e "${GREEN}  [ OK ]  $*${NC}"; }
info(){ echo -e "${CYAN}  [>>]   $*${NC}"; }
die() { echo -e "${RED}  [!!]   $*${NC}"; exit 1; }

ES_VERSION="8.13.0"
ES_DIR="$ROOT/elasticsearch/server/elasticsearch-${ES_VERSION}"
ES_LOGS="$ROOT/elasticsearch/logs"
VENV="$ROOT/backend/.venv"

[[ -f "$ES_DIR/bin/elasticsearch" ]] || die "Elasticsearch not found — run Install-TreasureMap.sh first."
[[ -f "$VENV/bin/uvicorn" ]]         || die "Python venv not found — run Install-TreasureMap.sh first."
[[ -d "$ROOT/frontend/node_modules" ]] || die "node_modules not found — run Install-TreasureMap.sh first."

echo -e "\n  Starting TreasureMap…\n"

# ── Elasticsearch ─────────────────────────────────────────────────────────────
if ! curl -sf http://localhost:9200 >/dev/null 2>&1; then
    info "Starting Elasticsearch…"
    export ES_JAVA_OPTS="-Xms1g -Xmx1g"
    nohup "$ES_DIR/bin/elasticsearch" > "$ES_LOGS/es.log" 2>&1 &
    echo $! > "$ROOT/elasticsearch/es.pid"
    TIMEOUT=90; ELAPSED=0
    while [[ $ELAPSED -lt $TIMEOUT ]]; do
        sleep 5; ELAPSED=$((ELAPSED+5))
        STATUS=$(curl -sf http://localhost:9200/_cluster/health 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])" 2>/dev/null || echo "")
        [[ "$STATUS" == "green" || "$STATUS" == "yellow" ]] && break
        printf "."
    done; echo ""
    ok "Elasticsearch running → http://localhost:9200"
else
    ok "Elasticsearch already running"
fi

# ── Backend ───────────────────────────────────────────────────────────────────
info "Starting API (uvicorn --reload)…"
(cd "$ROOT/backend" && "$VENV/bin/uvicorn" main:app --reload --host 0.0.0.0 --port 8000 > /tmp/tm-api.log 2>&1) &
echo $! > /tmp/tm-api.pid
sleep 3
ok "Backend running → http://localhost:8000"

# ── Frontend ──────────────────────────────────────────────────────────────────
info "Starting frontend (Vite dev server)…"
(cd "$ROOT/frontend" && npm run dev > /tmp/tm-ui.log 2>&1) &
echo $! > /tmp/tm-ui.pid
sleep 3
ok "Frontend running → http://localhost:5173"

# ── Open browser ──────────────────────────────────────────────────────────────
if command -v xdg-open &>/dev/null; then
    xdg-open "http://localhost:5173" &>/dev/null &
elif command -v wslview &>/dev/null; then
    wslview "http://localhost:5173" &>/dev/null &
fi

echo -e "${GREEN}"
cat << 'DONE'
  TreasureMap is running!
    UI       →  http://localhost:5173
    API docs →  http://localhost:8000/docs
    ES       →  http://localhost:9200

  Logs:
    API      →  /tmp/tm-api.log
    UI       →  /tmp/tm-ui.log
    ES       →  elasticsearch/logs/es.log

  Stop with:  ./Stop-TreasureMap.sh

DONE
echo -e "${NC}"
