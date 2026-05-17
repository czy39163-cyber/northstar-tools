# ChatGPT Feishu Bridge (大龙虾)

Browser extension that auto-sends prompts to ChatGPT web, captures responses, and forwards them to a Feishu custom bot.

## How It Works

```
User (popup) → Content Script (chatgpt.com) → ChatGPT responds
    → Content Script captures response → Background SW → Feishu webhook → 大龙虾
```

1. Open chatgpt.com in a browser tab
2. Click the extension icon, enter a prompt, click Send
3. The extension types the prompt into ChatGPT and presses send
4. When ChatGPT finishes responding, the response is captured
5. The response is forwarded to the configured Feishu webhook as an interactive card

## Installation

1. Open `chrome://extensions` (or `edge://extensions`)
2. Enable "Developer mode"
3. Click "Load unpacked" and select the `chatgpt-feishu-bridge` folder
4. The extension icon appears in the toolbar

## Configuration

1. Right-click the extension icon → **Options**, or click **Settings** in the popup
2. Enter your Feishu custom bot webhook URL:
   - In Feishu, create a Custom Bot in your target group chat
   - Copy the webhook URL (format: `https://open.feishu.cn/open-apis/bot/v2/hook/xxx`)
3. Click **Test Webhook** to verify
4. Adjust behavior settings as needed:
   - **Auto-send**: forward responses to Feishu automatically
   - **Prompt Prefix**: text prepended to every prompt (useful for system instructions)
   - **Max Response Length**: truncation threshold (default 50,000 chars)

## Usage

### Sending a prompt

1. Open `https://chatgpt.com` in a tab
2. Click the extension icon
3. Type your prompt (or paste)
4. Press **Enter** or click **Send to ChatGPT**
5. Wait for the status to show "Sent to Feishu"

### Keyboard shortcuts

- **Enter** in the prompt input: send
- **Shift+Enter**: new line in the prompt

### States

| State | Meaning |
|-------|---------|
| Ready | Idle, waiting for input |
| Sending to ChatGPT... | Injecting prompt into ChatGPT |
| Waiting for response... | ChatGPT is generating |
| Forwarding to Feishu... | Sending captured response to Feishu |
| Sent to Feishu | Complete |
| Error | Something went wrong (see error message) |

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "No ChatGPT tab found" | Open chatgpt.com in a browser tab first |
| "Not logged in" | Log into your ChatGPT account at chatgpt.com |
| "Feishu webhook not configured" | Go to Settings and enter your webhook URL |
| "Cannot find ChatGPT input" | ChatGPT UI may have changed — update selectors in `src/lib/selectors.js` |
| "Rate limited" | Wait a minute and try again |
| "Response timed out" | ChatGPT took too long; partial response sent if available |

## File Structure

```
chatgpt-feishu-bridge/
├── manifest.json            # Extension manifest (MV3)
├── icons/                   # Icon PNGs (16, 48, 128)
├── src/
│   ├── content.js           # ChatGPT DOM interaction
│   ├── background.js        # Service worker (router + Feishu)
│   ├── lib/
│   │   ├── config.js        # chrome.storage wrapper
│   │   ├── selectors.js     # ChatGPT DOM selectors
│   │   ├── feishu.js        # Feishu payload builder
│   │   └── logger.js        # Logging utility
│   ├── popup/               # Extension popup UI
│   └── options/             # Settings page
```

## Security

- No data is sent to third-party servers other than ChatGPT and the configured Feishu webhook
- The Feishu webhook URL is stored in chrome.storage.sync
- No API keys or secrets are embedded in the extension code
- All communication is over HTTPS
