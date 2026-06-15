#!/usr/bin/env bash
# TreasureMap — Linux setup script
# Install location: /mnt/d/Home-Lab/TreasureMap  (WSL)
#                   /d/Home-Lab/TreasureMap        (Git Bash)
#                   D:\Home-Lab\TreasureMap        (Windows host)
# Requires: Docker, Docker Compose v2, Python 3.12+, Node 20+
set -euo pipefail

# Resolve install root: prefer the fixed location, fall back to relative
if [ -d "/mnt/d/Home-Lab/TreasureMap" ]; then
    ROOT="/mnt/d/Home-Lab/TreasureMap"          # WSL
elif [ -d "/d/Home-Lab/TreasureMap" ]; then
    ROOT="/d/Home-Lab/TreasureMap"               # Git Bash
else
    ROOT="$(cd "$(dirname "$0")/.." && pwd)"     # fallback: relative to script
fi
cd "$ROOT"
echo "Working directory: $ROOT"

echo "======================================"
echo " TreasureMap Setup"
echo "======================================"

# 1. Start services
echo "[1/4] Starting Docker services…"
docker compose up -d --build

# 2. Wait for Elasticsearch
echo "[2/4] Waiting for Elasticsearch…"
until curl -sf http://localhost:9200/_cluster/health | grep -v '"status":"red"' > /dev/null; do
    printf '.'
    sleep 5
done
echo -e "\n  Elasticsearch is healthy."

# 3. Load sample data
echo "[3/4] Loading sample network data…"
cd backend
pip3 install -r requirements.txt -q
python3 ingest.py
cd ..

echo "[4/4] Done!"
echo ""
echo "  UI:        http://localhost:3000"
echo "  API docs:  http://localhost:8000/docs"
echo "  Kibana:    http://localhost:5601"
echo ""
echo "  For hot-reload dev:"
echo "    cd D:\\Home-Lab\\TreasureMap\\frontend && npm install && npm run dev"
echo "    cd D:\\Home-Lab\\TreasureMap\\backend  && uvicorn main:app --reload"
