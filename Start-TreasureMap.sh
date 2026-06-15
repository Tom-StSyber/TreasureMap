#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if command -v docker &>/dev/null && docker info &>/dev/null 2>&1; then
    cd "$SCRIPT_DIR" && docker compose up -d
    sleep 3
    command -v xdg-open &>/dev/null && xdg-open "http://localhost:3000" &>/dev/null & || true
else
    exec "$SCRIPT_DIR/scripts/ubuntu/start-native.sh"
fi
