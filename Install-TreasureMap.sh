#!/usr/bin/env bash
# ── TreasureMap — Ubuntu installer entry point ────────────────────────────────
# Double-click in Files ("Run as Program") or:  bash Install-TreasureMap.sh
#
# Prefers Docker Compose if docker is available; falls back to native install.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'

echo ""
echo -e "${CYAN}  ======================================================"
echo    "   TreasureMap — Ubuntu Installer"
echo -e "  ======================================================${NC}"
echo ""

if command -v docker &>/dev/null && docker info &>/dev/null 2>&1; then
    echo -e "${GREEN}  [FOUND] Docker is running. Using Docker Compose install.${NC}\n"
    cd "$SCRIPT_DIR"
    docker compose up -d --build

    echo -e "${CYAN}  Waiting for Elasticsearch…${NC}"
    TIMEOUT=120; ELAPSED=0
    while [[ $ELAPSED -lt $TIMEOUT ]]; do
        sleep 5; ELAPSED=$((ELAPSED+5))
        STATUS=$(curl -sf http://localhost:9200/_cluster/health 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])" 2>/dev/null || echo "")
        [[ "$STATUS" == "green" || "$STATUS" == "yellow" ]] && break
        printf "."
    done; echo ""

    LAB_DIR="$SCRIPT_DIR/data/synthetic-lab"
    echo -e "${CYAN}  Ingesting synthetic lab data…${NC}"
    curl -sf "http://localhost:8000/ingest/stream?folder_path=${LAB_DIR}&wipe=true" > /dev/null || \
        echo -e "  [WARN] Ingest failed — retry from the UI."

    # Open browser
    sleep 2
    command -v xdg-open &>/dev/null && xdg-open "http://localhost:3000" &>/dev/null & || true

    echo -e "${GREEN}\n  Done!  Open http://localhost:3000\n${NC}"
else
    echo -e "  [INFO] Docker not found. Using native install (no Docker required).\n"
    exec "$SCRIPT_DIR/scripts/ubuntu/native-install.sh"
fi
