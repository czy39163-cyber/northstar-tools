#!/usr/bin/env python3
"""CDP Message Injector — sends text to ChatGPT via Chrome DevTools Protocol.

Uses Input.dispatchKeyEvent for character-by-character typing that is
indistinguishable from real user input. GPT responds to this reliably.

Requires: Chrome with --remote-debugging-port=9222
Usage:   python3 cdp_inject.py "message text"
         echo "message" | python3 cdp_inject.py
"""

import sys, json, time, websocket

CDP_HOST = "127.0.0.1"
CDP_PORT = 9222
TYPING_DELAY = 0.03  # seconds between keystrokes (~33 chars/sec)

def find_chatgpt_tab():
    """Find the first ChatGPT tab's WebSocket URL."""
    import urllib.request
    resp = urllib.request.urlopen(f"http://{CDP_HOST}:{CDP_PORT}/json/list", timeout=5)
    tabs = json.loads(resp.read())
    for t in tabs:
        url = t.get('url', '')
        if 'chatgpt.com' in url or 'chat.openai.com' in url:
            return t.get('webSocketDebuggerUrl', '')
    return None

def type_text(ws, text: str):
    """Type text character by character into ChatGPT input, then press Enter."""
    # Focus the input
    ws.send(json.dumps({"id":1,"method":"Runtime.evaluate","params":{
        "expression": "var i=document.querySelector('#prompt-textarea');if(i){i.focus();i.click();'ok'}else{'no_input'}",
        "returnByValue": True
    }}))
    
    # Clear existing text (Ctrl+A, Backspace)
    ws.send(json.dumps({"id":2,"method":"Input.dispatchKeyEvent","params":{"type":"rawKeyDown","key":"a","windowsVirtualKeyCode":65,"modifiers":2}}))
    time.sleep(0.02)
    ws.send(json.dumps({"id":2,"method":"Input.dispatchKeyEvent","params":{"type":"rawKeyDown","key":"Backspace","windowsVirtualKeyCode":8,"modifiers":0}}))
    time.sleep(0.02)
    
    # Type character by character
    for c in text:
        ws.send(json.dumps({"id":2,"method":"Input.dispatchKeyEvent","params":{"type":"char","text":c,"key":c}}))
        time.sleep(TYPING_DELAY)
    
    # Press Enter to send
    time.sleep(0.1)
    ws.send(json.dumps({"id":3,"method":"Input.dispatchKeyEvent","params":{"type":"rawKeyDown","key":"Enter","windowsVirtualKeyCode":13,"text":"\r","unmodifiedText":"\r"}}))
    ws.send(json.dumps({"id":3,"method":"Input.dispatchKeyEvent","params":{"type":"char","text":"\r","key":"Enter"}}))
    ws.send(json.dumps({"id":3,"method":"Input.dispatchKeyEvent","params":{"type":"keyUp","key":"Enter","windowsVirtualKeyCode":13,"text":"\r"}}))

def main():
    # Read text from args or stdin
    text = ' '.join(sys.argv[1:]) if len(sys.argv) > 1 else sys.stdin.read().strip()
    if not text:
        print("Usage: cdp_inject.py <text>")
        sys.exit(1)
    
    ws_url = find_chatgpt_tab()
    if not ws_url:
        print("ERROR: No ChatGPT tab found")
        sys.exit(1)
    
    ws = websocket.create_connection(ws_url, timeout=10)
    ws.settimeout(2)
    type_text(ws, text)
    ws.close()
    print(f"[cdp] injected {len(text)} chars")

if __name__ == '__main__':
    main()
