#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if command -v docker &>/dev/null && docker info &>/dev/null 2>&1; then
    cd "$SCRIPT_DIR" && docker compose down
else
    exec "$SCRIPT_DIR/scripts/ubuntu/stop-native.sh"
fi
