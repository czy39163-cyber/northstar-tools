#!/bin/bash
# bridge_send.sh — Send message to ChatGPT via bridge
# Usage: bridge_send.sh [--chat-id CHAT_ID] "message text"
#        echo "message" | bridge_send.sh [--chat-id CHAT_ID]

CHAT_ID=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --chat-id) CHAT_ID="$2"; shift 2 ;;
        *) MSG="$1"; shift ;;
    esac
done
MSG="${MSG:-$(cat)}"
if [ -z "$MSG" ]; then
    echo "Usage: bridge_send.sh [--chat-id CHAT_ID] \"message text\""
    exit 1
fi

if [ -n "$CHAT_ID" ]; then
    curl -s -X POST http://127.0.0.1:18640/send \
        -H "Content-Type: application/json" \
        -d "$(python3 -c "import json,sys; print(json.dumps({'text': sys.argv[1], 'sender': 'CY', 'chat_id': sys.argv[2]}))" "$MSG" "$CHAT_ID")"
else
    curl -s -X POST http://127.0.0.1:18640/send \
        -H "Content-Type: application/json" \
        -d "$(python3 -c "import json,sys; print(json.dumps({'text': sys.argv[1], 'sender': 'CY'}))" "$MSG")"
fi

echo ""
