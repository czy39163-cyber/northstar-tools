#!/usr/bin/env python3
"""Feishu-ChatGPT HTTP Bridge.

Extension polls GET /pending → sends to ChatGPT.
Messages are fed via POST /send (terminal, Hermes, or any script).
ChatGPT responses come back via POST /response from the extension,
and Hermes polls GET /response?chat_id=xxx to retrieve them.

Usage:
    python3 bridge_server.py [--port 18643]
"""

import json, time, signal, sys, os, uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs



PORT = 18640
PENDING_TTL = 600  # auto-expire pending messages after 10 minutes

class PendingStore:
    """ACK-based pending message store with TTL expiry.

    Messages are returned with unique IDs. The consumer must ACK them
    to remove them from the store. Un-ACKed messages auto-expire after
    PENDING_TTL seconds to prevent stale accumulation.
    """

    def __init__(self):
        self._msgs = {}      # id → {text, sender, chat_id, ts}
        self._order = []     # FIFO order of IDs
        self._lock = __import__('threading').Lock()

    def put(self, entry: dict) -> str:
        """Add a message, return its ID."""
        msg_id = uuid.uuid4().hex[:12]
        entry["_id"] = msg_id
        with self._lock:
            self._msgs[msg_id] = entry
            self._order.append(msg_id)
        return msg_id

    def qsize(self) -> int:
        return len(self._msgs)

    def get_all(self) -> list:
        """Peek all messages (with IDs), auto-purge expired. Does NOT drain."""
        now = time.time()
        expired = []
        with self._lock:
            for mid in list(self._order):
                entry = self._msgs.get(mid)
                if entry and (now - entry["ts"]) > PENDING_TTL:
                    expired.append(mid)
            for mid in expired:
                self._msgs.pop(mid, None)
                self._order.remove(mid)
            return [self._msgs[mid] for mid in self._order if mid in self._msgs]

    def ack(self, ids: list) -> int:
        """Remove acknowledged messages by ID. Returns count removed."""
        removed = 0
        with self._lock:
            for mid in ids:
                if mid in self._msgs:
                    del self._msgs[mid]
                    self._order.remove(mid)
                    removed += 1
        return removed

    def empty(self) -> bool:
        return len(self._msgs) == 0

PENDING = PendingStore()
MESSAGE_LOG = []

# Response store: chat_id → deque of {text, ts}
RESPONSES = {}




class BridgeHTTP(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _json(self, code, data):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._json(200, {})

    def do_POST(self):
        path = urlparse(self.path).path

        if path == '/send':
            self._handle_send()
        elif path == '/pending/ack':
            self._handle_pending_ack()
        elif path == '/response':
            self._handle_response()
        else:
            self._json(404, {})

    def _handle_send(self):
        length = int(self.headers.get('Content-Length', 0))
        raw = self.rfile.read(length).decode() if length else '{}'
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            self._json(400, {'error': 'invalid json'})
            return
        text = (msg.get('text') or '').strip()
        if not text:
            self._json(400, {'error': 'empty'})
            return
        # Skip self-sent webhook messages
        if 'Sent by ChatGPT Feishu Bridge' in text or 'ChatGPT Response' in text:
            self._json(200, {'status': 'skipped', 'reason': 'self-sent'})
            return

        entry = {
            'text': text,
            'sender': msg.get('sender', ''),
            'chat_id': msg.get('chat_id', ''),
            'ts': time.time(),
        }
        msg_id = PENDING.put(entry)
        MESSAGE_LOG.append(entry)
        if len(MESSAGE_LOG) > 200:
            MESSAGE_LOG.pop(0)

        print(f"[+] QUEUED [{PENDING.qsize()}] id={msg_id} chat={msg.get('chat_id','?')} from {msg.get('sender','?'):12s} | {text[:70]}")
        self._json(200, {'status': 'queued', 'queue': PENDING.qsize(), 'id': msg_id})

    def _handle_pending_ack(self):
        """POST /pending/ack — acknowledge processed message IDs."""
        length = int(self.headers.get('Content-Length', 0))
        raw = self.rfile.read(length).decode() if length else '{}'
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            self._json(400, {'error': 'invalid json'})
            return
        ids = msg.get('ids', [])
        if not ids or not isinstance(ids, list):
            self._json(400, {'error': 'ids array required'})
            return
        removed = PENDING.ack(ids)
        print(f"[+] ACK removed={removed}/{len(ids)} ids={ids[:5]}{'...' if len(ids) > 5 else ''}")
        self._json(200, {'status': 'acked', 'removed': removed})

    def _handle_response(self):
        """Receive ChatGPT response from extension.

        If the response contains loop markers (@MAIN:, ##TASK_DONE##, ##PROJECT_CLOSED##),
        store under the \"gpt_loop\" key for the controller to poll.
        Otherwise store under the message's own chat_id.
        """
        length = int(self.headers.get('Content-Length', 0))
        raw = self.rfile.read(length).decode() if length else '{}'
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            self._json(400, {'error': 'invalid json'})
            return
        chat_id = (msg.get('chat_id') or '').strip()
        text = (msg.get('text') or '').strip()
        if not chat_id or not text:
            self._json(400, {'error': 'chat_id and text required'})
            return

        # Always log incoming /response so we can diagnose dropped GPT replies
        has_ma = '@MAIN:' in text
        has_done = '##TASK_DONE##' in text
        print(f"[+] RESPONSE chat={chat_id} len={len(text)} has_MAIN={has_ma} has_DONE={has_done} | {text[:100]}")

        # Simplified loop-marker detection — no GptLoopEngine dependency
        has_loop_marker = "@MAIN:" in text or "##TASK_DONE##" in text or "##PROJECT_CLOSED##" in text
        store_key = "gpt_loop" if has_loop_marker else chat_id
        if store_key not in RESPONSES:
            RESPONSES[store_key] = []
        RESPONSES[store_key].append({'text': text, 'ts': time.time()})
        self._json(200, {'status': 'stored'})




    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if path == '/health':
            self._json(200, {'status': 'ok', 'queue': PENDING.qsize()})
            return
        if path == '/pending':
            msgs = PENDING.get_all()
            self._json(200, {'messages': msgs})
            return
        if path == '/response':
            chat_id = params.get('chat_id', [None])[0]
            if not chat_id:
                self._json(400, {'error': 'chat_id query param required'})
                return
            msgs = RESPONSES.pop(chat_id, [])
            self._json(200, {'messages': msgs})
            return
        if path == '/log':
            self._json(200, {'log': MESSAGE_LOG[-20:]})
            return
        self._json(404, {})

    def do_DELETE(self):
        self._json(200, {'status': 'ok'})


def main():
    server = HTTPServer(('127.0.0.1', PORT), BridgeHTTP)
    print(f"[bridge] HTTP on http://127.0.0.1:{PORT}")
    print(f"[bridge] Extension polls GET /pending every 60s")
    print(f"[bridge]")
    print(f"[bridge] Send messages: curl -X POST http://127.0.0.1:{PORT}/send \\")
    print(f"[bridge]     -H 'Content-Type: application/json' \\")
    print(f"[bridge]     -d '{{\"text\":\"hello\",\"sender\":\"CY\",\"chat_id\":\"oc_xxx\"}}'")
    print(f"[bridge]")
    print(f"[bridge] Return responses: curl -X POST http://127.0.0.1:{PORT}/response \\")
    print(f"[bridge]     -H 'Content-Type: application/json' \\")
    print(f"[bridge]     -d '{{\"chat_id\":\"oc_xxx\",\"text\":\"ChatGPT response\"}}'")

    def shutdown(sig, frame):
        print("\n[bridge] Shutting down")
        server.shutdown()
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass

if __name__ == '__main__':
    main()
