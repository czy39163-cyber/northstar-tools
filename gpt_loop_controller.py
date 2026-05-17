#!/usr/bin/env python3
"""GPT-Loop Controller — Full lifecycle management for GPT→MAIN autonomous loops.

Command-line interface:
    python3 gpt_loop_controller.py start "task description"
    python3 gpt_loop_controller.py status
    python3 gpt_loop_controller.py pause
    python3 gpt_loop_controller.py resume
    python3 gpt_loop_controller.py stop

This controller polls Bridge Server for GPT responses with @MAIN: instructions,
executes them via the MAIN API, and sends results back to GPT through Bridge.
"""

from __future__ import annotations

import json
import os
import re
import signal
import sys
import time
import uuid
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import URLError

# ---------------------------------------------------------------------------
# Import gpt_loop utilities from bridge directory
# ---------------------------------------------------------------------------
_BRIDGE_DIR = "/home/cy/northstar-tools/browser-ext/bridge"
if _BRIDGE_DIR not in sys.path:
    sys.path.insert(0, _BRIDGE_DIR)

from gpt_loop import check_safety, strip_feishu_wrapper, RoundRecord

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
STATE_DIR = os.path.expanduser("~/.hermes/gpt_loop")
STATE_FILE = os.path.join(STATE_DIR, "controller_state.json")
ARCHIVE_DIR = os.path.join(STATE_DIR, "archive")
ENV_FILE = os.path.expanduser("~/.hermes/profiles/main/.env")

BRIDGE_URL = "http://127.0.0.1:18640"
MAIN_API_URL = "http://127.0.0.1:18642/v1/chat/completions"

# Claude API (Anthropic-compatible via DeepSeek)
CLAUDE_API_URL = os.getenv("ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic") + "/v1/messages"
CLAUDE_API_KEY = os.getenv("ANTHROPIC_AUTH_TOKEN", "")
CLAUDE_MODEL = os.getenv("ANTHROPIC_MODEL", "deepseek-v4-pro[1m]")

# Feishu webhook for progress reporting
FEISHU_WEBHOOK_FILE = os.path.expanduser("~/.hermes/gpt_loop/feishu_webhook.txt")
FEISHU_WEBHOOK_URL = ""
try:
    with open(FEISHU_WEBHOOK_FILE) as f:
        FEISHU_WEBHOOK_URL = f.read().strip()
except Exception:
    pass

# Feishu candidate skills table cache
FEISHU_TABLE_BASE = "Vbf2bkCbKaiklDsAaK5crvFOnAg"
FEISHU_TABLE_ID = "tblB4EK4wwf3Zft0"
FEISHU_TABLE_CACHE = os.path.expanduser("~/.hermes/gpt_loop/candidate_skills.json")

def _fetch_candidate_skills(api_key: str) -> str:
    """Fetch candidate skills via MAIN API (one slow call, cached 1 hour)."""
    try:
        # Check cache first
        if os.path.exists(FEISHU_TABLE_CACHE):
            mtime = os.path.getmtime(FEISHU_TABLE_CACHE)
            if time.time() - mtime < 3600:
                with open(FEISHU_TABLE_CACHE) as f:
                    cached = json.load(f)
                if cached.get("records"):
                    return _format_table_summary(cached["records"])

        # Call MAIN API to read the table
        result = _call_main_api(api_key,
            "读取飞书多维表格「候选技能清单」的全部记录。base_token=Vbf2bkCbKaiklDsAaK5crvFOnAg，table_id=tblB4EK4wwf3Zft0。"
            "只读，不要修改。以紧凑格式列出：名称、推荐指数、状态、描述、record_id。")
        if result.get("success"):
            # Parse MAIN's response into records
            text = result.get("content", "")
            records = _parse_table_from_text(text)
            if records:
                os.makedirs(os.path.dirname(FEISHU_TABLE_CACHE), exist_ok=True)
                with open(FEISHU_TABLE_CACHE, "w") as f:
                    json.dump({"records": records, "updated": _now_iso()}, f)
                return _format_table_summary(records)
    except Exception as e:
        _log("table_fetch_error", error=str(e))
    return ""

def _parse_table_from_text(text: str) -> list:
    """Parse MAIN's table response into records list."""
    records = []
    for line in text.split("\n"):
        if "|" in line and "名称" not in line:
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 3 and parts[0]:
                records.append({"fields": {
                    "名称": parts[0] if len(parts) > 0 else "",
                    "推荐指数": parts[1] if len(parts) > 1 else "",
                    "状态": parts[2] if len(parts) > 2 else "",
                    "一句话价值": parts[3] if len(parts) > 3 else "",
                }, "record_id": parts[-1] if len(parts) > 4 else ""})
    return records

def _format_table_summary(records: list) -> str:
    """Format table records as a compact text summary for DeepSeek."""
    lines = [f"## 候选技能清单 ({len(records)} 条)\n"]
    for r in records:
        f = r.get("fields", {})
        name = f.get("名称", "?")
        stars = f.get("推荐指数", "?")
        status = f.get("状态", "?")
        desc = (f.get("一句话价值", "") or f.get("描述", ""))[:80]
        record_id = r.get("record_id", "")
        lines.append(f"- {name} | ⭐{stars} | {status} | {desc} | id:{record_id[-8:]}")
    return "\n".join(lines)

POLL_INTERVAL = 3  # seconds between Bridge polls
LOOP_SLEEP = 1     # seconds between rounds
MAX_ROUNDS = 50
COMPACT_THRESHOLD = 10
RECENT_ROUNDS_KEEP = 3
MAX_FORMAT_ERRORS = 3
MAIN_API_TIMEOUT = 300
RETRY_COUNT = 1     # retries on MAIN API failure

DEFAULT_STATE = {
    "state": "idle",
    "task_id": "",
    "task": "",
    "round": 0,
    "max_rounds": MAX_ROUNDS,
    "completed_steps": [],
    "current_step": "",
    "recent_rounds": [],
    "compacted_rounds": 0,
    "consecutive_errors": 0,
    "chat_id": "gpt_loop",
    "started_at": "",
    "updated_at": "",
}

# System prompt sent to MAIN API with each instruction
SYSTEM_PROMPT = (
    "You are an autonomous task execution agent in the North Star system. "
    "You receive instructions from the GPT loop controller (which relays requests from ChatGPT). "
    "Execute the instruction precisely and return a concise, actionable result.\n\n"
    "SAFETY BOUNDARIES:\n"
    "- NEVER read, output, or transmit actual API keys, tokens, secrets, or credentials.\n"
    "- NEVER modify files outside the designated workspace (/home/cy/northstar-tools).\n"
    "- NEVER broadcast messages to all staff or full Feishu groups.\n"
    "- NEVER restart gateway services or modify production infrastructure.\n"
    "- ALWAYS use relative paths within the workspace, never absolute system paths.\n"
    "If an instruction would violate these boundaries, refuse and explain why."
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def _task_id() -> str:
    return "gpt_loop_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

LOG_FILE = os.path.expanduser("~/.hermes/gpt_loop/controller.log")

def _log(action: str, **kwargs):
    ts = _now_iso()
    parts = [f"[{ts}] action={action}"]
    for k, v in kwargs.items():
        parts.append(f"{k}={v}")
    line = " ".join(parts)
    print(line, flush=True)
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _load_env_api_key() -> str:
    """Read API_SERVER_KEY from ~/.hermes/profiles/main/.env ."""
    if not os.path.isfile(ENV_FILE):
        _log("env_error", error="ENV_FILE_NOT_FOUND", path=ENV_FILE)
        sys.exit(1)
    with open(ENV_FILE, "r") as f:
        for line in f:
            line = line.strip()
            if line.startswith("API_SERVER_KEY="):
                parts = line.split("=", 1)
                if len(parts) == 2:
                    return parts[1].strip()
    _log("env_error", error="API_SERVER_KEY_NOT_FOUND")
    sys.exit(1)


def _load_state() -> dict:
    """Load state from file, returning defaults if not found."""
    if os.path.isfile(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                state = json.load(f)
                # Ensure all default keys exist
                for k, v in DEFAULT_STATE.items():
                    state.setdefault(k, v)
                return state
        except (json.JSONDecodeError, OSError) as e:
            _log("state_load_error", error=str(e))
    return dict(DEFAULT_STATE)


def _save_state(state: dict):
    """Persist state to JSON file."""
    state["updated_at"] = _now_iso()
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def _archive_state(state: dict):
    """Copy current state to archive with task_id as filename."""
    task_id = state.get("task_id", "unknown")
    if not task_id:
        return
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    archive_path = os.path.join(ARCHIVE_DIR, f"{task_id}.json")
    # Don't overwrite existing archives
    if not os.path.isfile(archive_path):
        with open(archive_path, "w") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        _log("archived", path=archive_path)


def _compact_rounds(state: dict):
    """Compact old rounds when exceeding threshold, keeping recent N."""
    rounds = state.get("recent_rounds", [])
    if len(rounds) <= COMPACT_THRESHOLD:
        return
    # Keep only the last RECENT_ROUNDS_KEEP
    keep = rounds[-RECENT_ROUNDS_KEEP:]
    old = rounds[:-RECENT_ROUNDS_KEEP]
    # Create summary of old rounds
    summary_parts = []
    for r in old:
        summary_parts.append(
            f"Round {r['round_num']}: {r.get('status','?')} "
            f"instruction={r.get('main_instruction','')[:60]}"
        )
    compacted = state.get("compacted_rounds", 0) + len(old)
    state["recent_rounds"] = keep
    state["compacted_rounds"] = compacted
    if summary_parts:
        state["current_step"] = f"[compacted {len(old)} rounds] " + "; ".join(summary_parts)


# ---------------------------------------------------------------------------
# Claude API (replaces CDP + ChatGPT browser automation)
# ---------------------------------------------------------------------------

def _claude_send_and_receive(prompt: str) -> str:
    """Send prompt to Claude API (DeepSeek Anthropic-compatible) and return response text."""
    if not CLAUDE_API_KEY:
        raise RuntimeError("ANTHROPIC_AUTH_TOKEN not set")
    system = (
        "You are an autonomous task orchestrator. You guide MAIN (大龙虾) to complete tasks step by step. "
        "Reply ONLY with: @MAIN: <instruction> to execute a step, or ##TASK_DONE## when complete. "
        "Never explain, never chat, never stay silent. One instruction at a time. Be concise.\n\n"
        "CRITICAL RULES:\n"
        "- Make decisions with data you already have. Do NOT request repeated data display.\n"
        "- At most 2 rounds for information gathering, then DECIDE and ACT.\n"
        "- Before installing ANYTHING, first check if already installed (ask MAIN: 'check if X is installed').\n"
        "- NEVER re-clone, re-install, or re-download something that already exists.\n"
        "- If MAIN reports tool limit reached, re-issue the SAME instruction next round.\n"
        "- When all subtasks complete, output ##TASK_DONE## immediately."
    )
    payload = json.dumps({
        "model": CLAUDE_MODEL,
        "max_tokens": 4000,
        "system": system,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = Request(CLAUDE_API_URL, data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {CLAUDE_API_KEY}"},
        method="POST")
    with urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode())
    # Extract content from Anthropic-style response
    content = ""
    for block in data.get("content", []):
        if block.get("type") == "text":
            content += block.get("text", "")
    # Fallback: OpenAI-compatible response format
    if not content:
        choices = data.get("choices", [])
        if choices:
            content = choices[0].get("message", {}).get("content", "")
    return content.strip()

# ---------------------------------------------------------------------------
# CDP helpers (kept for fallback but no longer primary)
# ---------------------------------------------------------------------------

def _cdp_type_text(ws, text: str):
    """Type text character-by-character via CDP Input.dispatchKeyEvent."""
    for c in text:
        ws.send(json.dumps({"id": 99, "method": "Input.dispatchKeyEvent",
            "params": {"type": "char", "text": c, "key": c}}))
        time.sleep(0.03)

def _cdp_press_enter(ws):
    """Press Enter via CDP."""
    ws.send(json.dumps({"id": 99, "method": "Input.dispatchKeyEvent",
        "params": {"type": "rawKeyDown", "key": "Enter", "windowsVirtualKeyCode": 13, "text": "\r", "unmodifiedText": "\r"}}))
    ws.send(json.dumps({"id": 99, "method": "Input.dispatchKeyEvent",
        "params": {"type": "char", "text": "\r", "key": "Enter"}}))
    ws.send(json.dumps({"id": 99, "method": "Input.dispatchKeyEvent",
        "params": {"type": "keyUp", "key": "Enter", "windowsVirtualKeyCode": 13, "text": "\r"}}))
    time.sleep(0.3)
    # Clear residual text via keyboard: Ctrl+A, Backspace
    ws.send(json.dumps({"id": 99, "method": "Input.dispatchKeyEvent",
        "params": {"type": "rawKeyDown", "key": "a", "windowsVirtualKeyCode": 65, "modifiers": 2}}))
    time.sleep(0.05)
    ws.send(json.dumps({"id": 99, "method": "Input.dispatchKeyEvent",
        "params": {"type": "rawKeyDown", "key": "Backspace", "windowsVirtualKeyCode": 8}}))
    time.sleep(0.05)

def _bridge_send(text: str, sender: str = "gpt_loop", chat_id: str = "gpt_loop") -> dict:
    """Inject message into ChatGPT via CDP, and also POST to Bridge /send for ACK tracking."""
    # 1. Inject via CDP (primary - GPT responds to this)
    try:
        import websocket
        # Find ChatGPT tab
        resp = urlopen(f"http://127.0.0.1:9222/json/list", timeout=5)
        tabs = json.loads(resp.read())
        ws_url = None
        for t in tabs:
            if 'chatgpt.com' in t.get('url', '') or 'chat.openai.com' in t.get('url', ''):
                ws_url = t.get('webSocketDebuggerUrl', '')
                break
        if ws_url:
            ws = websocket.create_connection(ws_url, timeout=10)
            ws.settimeout(2)
            # Focus input
            ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate", "params": {
                "expression": "var i=document.querySelector('#prompt-textarea');if(i){i.focus();i.click();'ok'}else{'no'}",
                "returnByValue": True}}))
            time.sleep(0.1)
            # Clear any residual text (Ctrl+A, Backspace)
            ws.send(json.dumps({"id": 98, "method": "Input.dispatchKeyEvent",
                "params": {"type": "rawKeyDown", "key": "a", "windowsVirtualKeyCode": 65, "modifiers": 2}}))
            time.sleep(0.03)
            ws.send(json.dumps({"id": 98, "method": "Input.dispatchKeyEvent",
                "params": {"type": "rawKeyDown", "key": "Backspace", "windowsVirtualKeyCode": 8}}))
            time.sleep(0.05)
            # Type the text
            _cdp_type_text(ws, text)
            time.sleep(0.3)
            # Press Enter to send
            _cdp_press_enter(ws)
            ws.close()
            _log("cdp_inject", length=len(text))
    except Exception as e:
        _log("cdp_inject_error", error=str(e))

    # 2. CDP-only mode — skip Bridge queue to avoid double injection by extension
    return {"status": "cdp_injected", "length": len(text)}


# Track the CDP assistant message count for change detection
_cdp_last_asst_count = 0
_cdp_last_asst_text = ""

def _cdp_get_asst_state():
    """Get current assistant message count and last text via CDP. Returns (count, text)."""
    try:
        import websocket
        resp = urlopen("http://127.0.0.1:9222/json/list", timeout=5)
        tabs = json.loads(resp.read())
        ws_url = None
        for t in tabs:
            if 'chatgpt.com' in t.get('url', '') or 'chat.openai.com' in t.get('url', ''):
                ws_url = t.get('webSocketDebuggerUrl', '')
                break
        if not ws_url:
            return 0, ""
        ws = websocket.create_connection(ws_url, timeout=5)
        ws.settimeout(2)
        ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate", "params": {
            "expression": '''
(function() {
  var all = document.querySelectorAll('div[data-message-author-role="assistant"]');
  if (all.length === 0) return {count:0, text:"", stop:false};
  var last = all[all.length-1];
  var c = last.querySelector('div.markdown') || last.querySelector('div[class*="markdown"]') || last;
  var stopBtn = document.querySelector('button[data-testid="stop-button"]') || document.querySelector('button[aria-label*="Stop"]');
  return {count: all.length, text: (c.textContent||"").trim(), stop: !!stopBtn};
})()
            ''', "returnByValue": True}}))
        for _ in range(3):
            try:
                r = json.loads(ws.recv())
                if r.get('id') == 1:
                    val = r.get('result', {}).get('result', {}).get('value', {})
                    count = val.get('count', 0)
                    text = val.get('text', '')
                    stop = val.get('stop', True)
                    ws.close()
                    return count, text, stop
            except: pass
        try: ws.close()
        except: pass
    except: pass
    return 0, "", False

def _cdp_check_response() -> list:
    """Check ChatGPT DOM via CDP for new assistant messages. Waits for stability. Posts to Bridge."""
    global _cdp_last_asst_count, _cdp_last_asst_text
    count, text, stop = _cdp_get_asst_state()
    if count == 0:
        return []
    # Check if there's a new or changed response
    if count == _cdp_last_asst_count and text == _cdp_last_asst_text:
        return []
    if len(text) < 20:
        return []  # Too short — GPT still generating
    # Wait for stability: stop button gone AND text unchanged for 3 seconds
    if stop:
        return []  # GPT still generating (stop button visible)
    _log("cdp_stability_wait", length=len(text))
    time.sleep(3)
    _, text2, stop2 = _cdp_get_asst_state()
    if stop2 or len(text2) < 20 or text2 != text:
        return []  # Still changing or too short
    # Stable — capture it
    _cdp_last_asst_count = count
    _cdp_last_asst_text = text
    try:
        payload = json.dumps({"chat_id": "gpt_loop", "text": text}).encode()
        req = Request(f"{BRIDGE_URL}/response", data=payload,
            headers={"Content-Type": "application/json"}, method="POST")
        urlopen(req, timeout=5)
        _log("cdp_response_captured", length=len(text))
    except: pass
    return [{"text": text, "ts": time.time()}]

def _feishu_progress(text: str):
    """Post progress to Feishu via webhook."""
    if not FEISHU_WEBHOOK_URL:
        return
    try:
        payload = json.dumps({"msg_type": "text", "content": {"text": text}}).encode()
        req = Request(FEISHU_WEBHOOK_URL, data=payload,
            headers={"Content-Type": "application/json"}, method="POST")
        urlopen(req, timeout=10)
    except Exception:
        pass

def _bridge_queue_only(text: str, sender: str = "gpt_loop", chat_id: str = "gpt_loop") -> dict:
    """Queue a message to Bridge /send WITHOUT CDP injection (for quiet reminders)."""
    payload = json.dumps({"text": text, "sender": sender, "chat_id": chat_id}).encode()
    req = Request(f"{BRIDGE_URL}/send", data=payload,
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return {"status": "queued", "note": "no_response"}

def _bridge_poll_response(chat_id: str = "gpt_loop") -> list:
    """Poll Bridge /response + CDP for GPT responses. Returns list of message dicts."""
    # 1. Check CDP first (primary - GPT responds to CDP injection)
    cdp_msgs = _cdp_check_response()
    if cdp_msgs:
        return cdp_msgs
    # 2. Fallback to Bridge
    try:
        req = Request(f"{BRIDGE_URL}/response?chat_id={chat_id}", method="GET")
        with urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            return data.get("messages", [])
    except Exception:
        return []


def _bridge_health() -> bool:
    """Check if Bridge is reachable."""
    try:
        req = Request(f"{BRIDGE_URL}/health", method="GET")
        with urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            return data.get("status") == "ok"
    except Exception:
        return False


def _call_main_api(api_key: str, instruction: str) -> dict:
    """Send instruction to MAIN API and return parsed response.

    Returns:
        dict with keys: success (bool), content (str), error (str or None)
    """
    payload = json.dumps({
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": instruction},
        ],
        "max_tokens": 4000,
    }).encode()
    req = Request(
        MAIN_API_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=MAIN_API_TIMEOUT) as resp:
            body = json.loads(resp.read().decode())
            content = body.get("choices", [{}])[0].get("message", {}).get("content", "")
            if not content:
                return {"success": False, "content": "", "error": "Empty MAIN response"}
            return {"success": True, "content": content, "error": None}
    except URLError as e:
        return {"success": False, "content": "", "error": str(e)}
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        return {"success": False, "content": "", "error": f"Parse error: {e}"}


# ---------------------------------------------------------------------------
# Safety helpers
# ---------------------------------------------------------------------------

def _safety_summary(result: dict) -> str:
    """Format safety check result as human-readable string."""
    level = result.get("level", "low")
    rule = result.get("rule", "none")
    reason = result.get("reason", "")
    if level == "low":
        return "PASS"
    return f"{level.upper()} ({rule}): {reason}"


# ---------------------------------------------------------------------------
# Controller Logic
# ---------------------------------------------------------------------------

def cmd_status():
    """Print current controller status."""
    state = _load_state()
    bridge_ok = _bridge_health()
    print(f"State:           {state.get('state', 'unknown')}")
    print(f"Task ID:         {state.get('task_id', 'N/A')}")
    print(f"Task:            {state.get('task', 'N/A')}")
    print(f"Round:           {state.get('round', 0)} / {state.get('max_rounds', MAX_ROUNDS)}")
    print(f"Compacted:       {state.get('compacted_rounds', 0)} rounds")
    print(f"Errors:          {state.get('consecutive_errors', 0)} consecutive")
    print(f"Recent rounds:   {len(state.get('recent_rounds', []))}")
    print(f"Steps completed: {len(state.get('completed_steps', []))}")
    print(f"Claude API:      {'✓' if CLAUDE_API_KEY else '✗'} ({CLAUDE_MODEL})")
    print(f"Updated:         {state.get('updated_at', 'N/A')}")


def cmd_start(task_desc: str):
    """Start a new GPT loop task."""
    api_key = _load_env_api_key()
    state = _load_state()

    # Check if already running
    if state.get("state") in ("running",):
        _log("start_aborted", reason="already_running", current_state=state["state"])
        print("ERROR: A loop is already running. Use 'stop' first or 'status' to check.")
        sys.exit(1)

    # Check Claude API credentials
    if not CLAUDE_API_KEY:
        print("ERROR: ANTHROPIC_AUTH_TOKEN not set")
        sys.exit(1)

    # Initialize new state
    now = _now_iso()
    tid = _task_id()
    state = {
        "state": "running",
        "task_id": tid,
        "task": task_desc,
        "round": 0,
        "max_rounds": MAX_ROUNDS,
        "completed_steps": [],
        "current_step": "initializing",
        "recent_rounds": [],
        "compacted_rounds": 0,
        "consecutive_errors": 0,
        "chat_id": "gpt_loop",
        "started_at": now,
        "updated_at": now,
    }
    _save_state(state)
    _log("started", task_id=tid, task=task_desc)

    # Pre-fetch candidate skills table if relevant (avoids slow MAIN lark API calls)
    table_data = ""
    if any(kw in task_desc for kw in ["候选技能", "飞书多维表格", "五星", "技能清单"]):
        table_data = _fetch_candidate_skills(api_key)
        _log("table_cache", length=len(table_data))

    initial_prompt = (
        f"## TASK ##\n"
        f"{task_desc}\n\n"
        f"{table_data}\n"
        f"## INSTRUCTIONS ##\n"
        f"Guide MAIN step by step. Each step: @MAIN: <instruction>\n"
        f"MAIN executes and reports back. Then decide next step.\n"
        f"The table data above is pre-loaded — do NOT ask MAIN to re-read it.\n"
        f"Skip data gathering. Go directly to selecting and installing.\n"
        f"When done, output ##TASK_DONE##.\n\n"
        f"Be concise. One step at a time."
    )
    try:
        _bridge_send(initial_prompt)
        _log("initial_prompt_sent", round=0)
    except Exception as e:
        _log("start_failed", error=str(e))
        state["state"] = "idle"
        _save_state(state)
        print(f"ERROR: Failed to send initial prompt to Bridge: {e}")
        sys.exit(1)

    # Enter the main loop
    _run_loop(state, api_key)


def _run_loop(state: dict, api_key: str):
    """Claude API loop: send prompts, receive @MAIN: instructions, execute, repeat."""
    _log("loop_enter")

    _running = [True]
    def _signal_handler(sig, frame):
        _running[0] = False
        print(f"\n[controller] Signal received, stopping...")
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    # Build initial prompt
    prompt = (
        f"## TASK ##\n{state['task']}\n\n"
        f"Reply with your first @MAIN: instruction to begin."
    )

    try:
        while _running[0] and state["state"] == "running":
            round_num = state["round"] + 1

            # 1. Call Claude API
            _log("claude_send", round=round_num-1, length=len(prompt))
            try:
                response = _claude_send_and_receive(prompt)
            except Exception as e:
                _log("claude_error", error=str(e))
                time.sleep(5)
                continue

            if not response:
                time.sleep(2)
                continue

            _log("claude_response", round=round_num-1, length=len(response))
            _log("claude_says", round=round_num-1, text=response[:300])

            # 2. Check termination
            if "##PROJECT_CLOSED##" in response:
                _finalize_done(state, "project_closed", api_key)
                return
            if "##TASK_DONE##" in response:
                _finalize_done(state, "task_done", api_key)
                return

            # 3. Extract @MAIN: instruction
            m = re.search(r"@MAIN:\s*(.+?)(?=\n##|\n@MAIN:|$)", response, re.DOTALL)
            if not m:
                state["consecutive_errors"] += 1
                _log("format_error", round=round_num-1, consecutive=state["consecutive_errors"])
                if state["consecutive_errors"] >= MAX_FORMAT_ERRORS:
                    state["state"] = "paused"
                    _save_state(state)
                    print("[controller] Loop paused: max format errors.")
                    return
                prompt = "## FORMAT REMINDER ##\nReply with @MAIN: <instruction> or ##TASK_DONE##."
                _save_state(state)
                continue

            state["consecutive_errors"] = 0
            instruction = m.group(1).strip()
            _log("instruction_extracted", round=round_num-1, instruction=instruction[:80])

            # 4. Safety check
            safety = check_safety(instruction, task=state.get("task", ""))
            _log("safety_check", level=safety.get("level","low"))
            if safety["level"] == "high":
                state["state"] = "paused"
                state["current_step"] = f"Safety HIGH: {safety['reason']}"
                _save_state(state)
                print(f"[controller] HIGH safety: {safety['reason']}")
                return

            # 5. Execute via MAIN API
            _log("main_api_call", round=round_num-1, attempt=1)
            main_result = _call_main_api(api_key, instruction)

            state["round"] = round_num

            # 6. Build next prompt for Claude
            if main_result.get("success"):
                state["completed_steps"].append(f"Round {round_num}: {instruction[:60]}...")
                _log("main_result", round=round_num, text=main_result['content'][:300])
                # Feishu progress
                _feishu_progress(
                    f"🔵 R{round_num} 完成\n\n"
                    f"DeepSeek 指令: {instruction[:150]}\n\n"
                    f"MAIN 结果: {main_result['content'][:200]}"
                )
                # Feishu progress: every round
                _feishu_post(api_key, f"🔵 R{round_num} 完成\n指令: {instruction[:100]}\n结果: {main_result['content'][:150]}")
                prompt = (
                    f"## TASK ##\n{state['task'][:200]}\n"
                    f"Round {round_num}/{state.get('max_rounds',MAX_ROUNDS)}\n\n"
                    f"## MAIN FEEDBACK ##\n{main_result['content'][:800]}\n\n"
                    f"Reply with your next @MAIN: instruction or ##TASK_DONE##."
                )
            else:
                prompt = (
                    f"## MAIN ERROR ##\nMAIN failed: {main_result.get('error','?')[:200]}\n"
                    f"Last instruction: {instruction[:150]}\n\n"
                    f"Re-issue @MAIN: instruction or ##TASK_DONE##."
                )

            _save_state(state)
            time.sleep(LOOP_SLEEP)

    except Exception as e:
        _log("loop_error", error=str(e))
        state["state"] = "idle"
        _save_state(state)
        raise

def _feishu_post(api_key: str, text: str):
    """Post a progress message to Feishu by asking MAIN to relay it."""
    try:
        msg = f"发送飞书消息（不调用工具，直接将以下内容作为你的回复）：\n{text}"
        _call_main_api(api_key, msg)
    except Exception:
        pass

def _finalize_done(state: dict, reason: str, api_key: str = ""):
    """Mark task as done, archive, save, generate report, notify Feishu."""
    state["state"] = "done"
    state["current_step"] = reason
    _save_state(state)
    _archive_state(state)
    _log("finalized", reason=reason, task_id=state.get("task_id", "?"))

    # Generate completion report
    report_path = os.path.join(STATE_DIR, "latest_report.md")
    steps = state.get("completed_steps", [])
    task = state.get("task", "?")
    summary = f"GPT-Loop 任务完成\n\n任务: {task}\n轮次: {state['round']}\n步骤: {len(steps)}项\n"
    lines = [
        f"# GPT-Loop 任务报告",
        f"",
        f"**任务**: {task}",
        f"**状态**: {'✅ 完成' if reason == 'task_done' else '🔒 项目关闭'}",
        f"**轮次**: {state['round']} 轮",
        f"**完成步骤**: {len(steps)}",
        f"",
        f"## 执行步骤",
    ]
    for s in steps:
        lines.append(f"- {s}")
    lines += [
        f"",
        f"## 注意事项",
        f"- 如有\"等待CY操作\"的步骤，需你手动处理",
        f"- 运行 `python3 ... report` 查看详细报告",
    ]
    try:
        with open(report_path, "w") as f:
            f.write("\n".join(lines) + "\n")
    except Exception:
        pass
    print(f"\n[controller] 报告已生成: {report_path}")

    # Notify Feishu via webhook
    _feishu_progress(
        f"✅ 任务完成\n\n"
        f"任务: {task}\n"
        f"轮次: {state['round']}\n"
        f"步骤: {len(steps)} 项\n\n"
        f"报告: python3 ... report"
    )


def cmd_pause():
    """Pause a running loop."""
    state = _load_state()
    if state.get("state") != "running":
        print(f"ERROR: Cannot pause. Current state is '{state.get('state', 'unknown')}'.")
        sys.exit(1)
    state["state"] = "paused"
    _save_state(state)
    _log("paused", round=state.get("round", 0))
    print("Loop paused.")
    print(f"Current round: {state.get('round', 0)}")
    print(f"Use 'resume' to continue or 'stop' to end.")


def cmd_resume():
    """Resume a paused loop."""
    state = _load_state()
    if state.get("state") != "paused":
        print(f"ERROR: Cannot resume. Current state is '{state.get('state', 'unknown')}'.")
        sys.exit(1)

    api_key = _load_env_api_key()

    # Check Bridge health
    if not _bridge_health():
        print("ERROR: Bridge is not reachable. Cannot resume.")
        sys.exit(1)

    state["state"] = "running"
    state["consecutive_errors"] = 0
    _save_state(state)
    _log("resumed", round=state.get("round", 0))
    print(f"Resumed at round {state.get('round', 0)}.")
    print(f"Task: {state.get('task', 'N/A')}")

    # Re-enter the loop
    _run_loop(state, api_key)


def cmd_report():
    """Print the latest task completion report."""
    report_path = os.path.join(STATE_DIR, "latest_report.md")
    if os.path.exists(report_path):
        with open(report_path, "r") as f:
            print(f.read())
    else:
        print("No report found. Tasks generate reports on completion.")

def cmd_stop():
    """Stop the current loop and archive."""
    state = _load_state()
    if state.get("state") in ("idle", "done"):
        print(f"Nothing to stop. Current state is '{state.get('state', 'unknown')}'.")
        return
    state["state"] = "done"
    state["current_step"] = "stopped by user"
    _save_state(state)
    _archive_state(state)
    _log("stopped", round=state.get("round", 0), task_id=state.get("task_id", "?"))
    print(f"Loop stopped at round {state.get('round', 0)}.")
    print(f"Task: {state.get('task', 'N/A')}")
    print(f"State archived as: {state.get('task_id', 'unknown')}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 gpt_loop_controller.py start \"task description\"")
        print("  python3 gpt_loop_controller.py status")
        print("  python3 gpt_loop_controller.py pause")
        print("  python3 gpt_loop_controller.py resume")
        print("  python3 gpt_loop_controller.py stop")
        sys.exit(1)

    command = sys.argv[1].lower()

    if command == "start":
        if len(sys.argv) < 3:
            print("ERROR: Missing task description. Usage: start \"task description\"")
            sys.exit(1)
        task_desc = " ".join(sys.argv[2:])
        cmd_start(task_desc)

    elif command == "status":
        cmd_status()

    elif command == "pause":
        cmd_pause()

    elif command == "resume":
        cmd_resume()

    elif command == "report":
        cmd_report()
    elif command == "stop":
        cmd_stop()

    else:
        print(f"ERROR: Unknown command '{command}'.")
        print("Usage: start | status | pause | resume | stop")
        sys.exit(1)


if __name__ == "__main__":
    main()
