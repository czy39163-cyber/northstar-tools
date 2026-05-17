#!/bin/bash
# run_bridge.sh — Start ChatGPT Feishu Bridge Server with correct API key
# Usage: ./run_bridge.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Load API_SERVER_KEY from Hermes main profile .env
ENV_FILE="$HOME/.hermes/profiles/main/.env"
if [ -f "$ENV_FILE" ]; then
    export $(grep "^API_SERVER_KEY=" "$ENV_FILE" | xargs)
fi

# Kill any existing bridge
pkill -f "python3 bridge_server.py" 2>/dev/null
sleep 1

# Start bridge with key in environment
cd "$SCRIPT_DIR"
nohup python3 bridge_server.py > /tmp/bridge.log 2>&1 &
PID=$!
sleep 2

# Verify
if kill -0 "$PID" 2>/dev/null && curl -s --max-time 2 http://127.0.0.1:18640/health > /dev/null 2>&1; then
    echo "[bridge] Started PID=$PID with API_SERVER_KEY=${API_SERVER_KEY:+(set)}"
else
    echo "[bridge] FAILED to start"
    exit 1
fi
