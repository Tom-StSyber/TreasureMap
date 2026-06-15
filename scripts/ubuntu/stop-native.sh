#!/usr/bin/env bash
# ── TreasureMap — stop all native services (Ubuntu) ──────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'
ok()  { echo -e "${GREEN}  [ OK ]  $*${NC}"; }
info(){ echo -e "${CYAN}  [>>]   $*${NC}"; }

echo -e "\n  Stopping TreasureMap services…\n"

stop_pid() {
    local pidfile="$1" name="$2"
    if [[ -f "$pidfile" ]]; then
        local pid; pid=$(cat "$pidfile")
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null && ok "$name (PID $pid) stopped"
        else
            info "$name was not running"
        fi
        rm -f "$pidfile"
    else
        # Fall back to pkill
        pkill -f "$3" 2>/dev/null && ok "$name stopped via pkill" || info "$name was not running"
    fi
}

stop_pid "/tmp/tm-ui.pid"  "Frontend (Vite)"    "vite"
stop_pid "/tmp/tm-api.pid" "Backend (uvicorn)"  "uvicorn"
stop_pid "$ROOT/elasticsearch/es.pid" "Elasticsearch" "elasticsearch"

echo -e "${GREEN}\n  All TreasureMap services stopped.\n${NC}"
