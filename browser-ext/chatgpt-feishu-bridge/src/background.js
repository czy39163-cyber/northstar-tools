// background.js — Service Worker for ChatGPT Feishu Bridge

// Config keys
var K_WEBHOOK = 'feishuWebhookUrl';
var K_AUTO = 'autoSendEnabled';
var K_PREFIX = 'promptPrefix';
var K_MAXLEN = 'maxResponseLength';

var DEFAULTS = {};
DEFAULTS[K_WEBHOOK] = '';
DEFAULTS[K_AUTO] = true;
DEFAULTS[K_PREFIX] = '';
DEFAULTS[K_MAXLEN] = 50000;

// State
var g_webhook = '';
var g_auto = true;
var g_ports = [];

// ---- Init ----
async function loadConfig() {
  var c = await chrome.storage.sync.get(DEFAULTS);
  g_webhook = c[K_WEBHOOK] || '';
  g_auto = c[K_AUTO] !== false;
}

loadConfig().catch(function (e) { console.log('[bg] Config load failed:', e.message); });


chrome.storage.onChanged.addListener(function (changes) {
  if (changes[K_WEBHOOK]) g_webhook = changes[K_WEBHOOK].newValue || '';
  if (changes[K_AUTO] !== undefined) g_auto = changes[K_AUTO].newValue !== false;
});

// ---- Popup connections ----
chrome.runtime.onConnect.addListener(function (port) {
  if (port.name !== 'popup') return;
  g_ports.push(port);
  port.onDisconnect.addListener(function () {
    g_ports = g_ports.filter(function (p) { return p !== port; });
  });
});

function broadcast(msg) {
  g_ports.forEach(function (p) { try { p.postMessage(msg); } catch (_) {} });
}

// ---- Message routing ----
chrome.runtime.onMessage.addListener(function (msg, sender, sendResponse) {
  if (msg.action === 'checkStatus') { onCheck(sendResponse); return true; }
  if (msg.action === 'sendPrompt') { onSend(msg.prompt, sendResponse); return true; }
  if (msg.action === 'cancelGeneration') { onCancel(sendResponse); return true; }
  if (msg.action === 'contentScriptStatus') { onContentStatus(msg); return false; }
  if (msg.action === 'openOptions') { chrome.runtime.openOptionsPage(); return false; }
  if (msg.action === 'testWebhook') { onTest(msg.url, sendResponse); return true; }
  return false;
});

// ---- Handlers ----
async function onCheck(sr) {
  try {
    var tabs = await chrome.tabs.query({ url: ['https://chatgpt.com/*', 'https://chat.openai.com/*'] });
    sr({ hasTab: tabs.length > 0, whOk: !!g_webhook, auto: g_auto });
  } catch (e) { sr({ error: e.message }); }
}

async function onSend(prompt, sr) {
  if (!prompt || !prompt.trim()) { sr({ status: 'error', code: 'EMPTY' }); return; }
  try {
    var tabs = await chrome.tabs.query({ url: ['https://chatgpt.com/*', 'https://chat.openai.com/*'] });
    if (!tabs.length) { sr({ status: 'error', code: 'NO_TAB', message: 'No ChatGPT tab open' }); broadcast({ action: 'statusUpdate', status: 'error', message: 'No ChatGPT tab found.' }); return; }
    var tabId = tabs[0].id;

    // Try ping first
    try {
      var pingResp = await chrome.tabs.sendMessage(tabId, { action: 'ping' });
      if (!pingResp || !pingResp.loggedIn) {
        sr({ status: 'error', code: 'NOT_LOGGED_IN', message: 'Not logged into ChatGPT.' });
        broadcast({ action: 'statusUpdate', status: 'error', message: 'Not logged into ChatGPT.' });
        return;
      }
    } catch (pingErr) {
      console.log('[bg] Content script not loaded, injecting dynamically...');
      // Content script not loaded — inject it dynamically
      try {
        await chrome.scripting.executeScript({ target: { tabId: tabId }, files: ['src/content.js'] });
        console.log('[bg] Dynamic injection done');
        // Wait a moment for the script to initialize
        await new Promise(function (r) { setTimeout(r, 300); });
        // Verify injection
        try {
          var ping2 = await chrome.tabs.sendMessage(tabId, { action: 'ping' });
          if (!ping2 || !ping2.loggedIn) {
            sr({ status: 'error', code: 'NOT_LOGGED_IN', message: 'Not logged into ChatGPT.' });
            broadcast({ action: 'statusUpdate', status: 'error', message: 'Not logged into ChatGPT.' });
            return;
          }
        } catch (e2) {
          console.log('[bg] Dynamic injection also failed:', e2.message);
          // Last resort: inject inline
          try {
            await chrome.scripting.executeScript({ target: { tabId: tabId }, func: injectedContentScript });
            await new Promise(function (r) { setTimeout(r, 500); });
            try {
              await chrome.tabs.sendMessage(tabId, { action: 'ping' });
            } catch (e3) {
              sr({ status: 'error', code: 'NO_CS', message: 'Cannot inject script. Try refreshing chatgpt.com.' });
              broadcast({ action: 'statusUpdate', status: 'error', message: 'Cannot connect to ChatGPT page. Refresh the tab.' });
              return;
            }
          } catch (e3) {
            sr({ status: 'error', code: 'NO_CS', message: 'Cannot inject script: ' + e3.message });
            broadcast({ action: 'statusUpdate', status: 'error', message: 'Cannot connect to ChatGPT page.' });
            return;
          }
        }
      } catch (e2) {
        console.log('[bg] Dynamic injection failed:', e2.message);
        sr({ status: 'error', code: 'NO_CS', message: 'Cannot inject content script.' });
        broadcast({ action: 'statusUpdate', status: 'error', message: 'Reload extension and refresh chatgpt.com tab.' });
        return;
      }
    }

    await chrome.tabs.sendMessage(tabId, { action: 'sendPrompt', prompt: prompt.trim() });
    sr({ status: 'accepted' });
    broadcast({ action: 'statusUpdate', status: 'waiting' });
  } catch (e) {
    console.log('[bg] Send failed:', e.message);
    sr({ status: 'error', code: 'FAIL', message: e.message });
    broadcast({ action: 'statusUpdate', status: 'error', message: e.message });
  }
}

// Fallback: inline content script for dynamic injection when file loading fails
function injectedContentScript() {
  if (window.__BRIDGE_INJECTED) return;
  window.__BRIDGE_INJECTED = true;
  console.log('[BRIDGE-INLINE] Injected dynamically');

  var g_timer = null;

  chrome.runtime.onMessage.addListener(function (msg, sender, sendResponse) {
    if (msg.action === 'ping') { sendResponse({ status: 'alive', loggedIn: true }); return true; }
    if (msg.action === 'sendPrompt') {
      sendResponse({ status: 'accepted' });
      var input = document.querySelector('#prompt-textarea') || document.querySelector('form textarea') || document.querySelector('[role="textbox"]') || document.querySelector('div[contenteditable="true"]');
      if (!input) { chrome.runtime.sendMessage({ action: 'contentScriptStatus', status: 'error', code: 'NO_INPUT', error: 'No input' }, function() {}); return false; }
      if (input.tagName === 'TEXTAREA' || input.tagName === 'INPUT') {
        var d = Object.getOwnPropertyDescriptor(input.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype, 'value');
        if (d && d.set) d.set.call(input, msg.prompt); else input.value = msg.prompt;
        input.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
      } else { input.focus(); input.textContent = msg.prompt; input.dispatchEvent(new InputEvent('input', { bubbles: true, composed: true })); }

      var sendAttempts = 0;
      var trySend = function () {
        var btn = document.querySelector('#composer-submit-button')
          || document.querySelector('button[data-testid="send-button"]')
          || document.querySelector('button[aria-label*="发送"]')
          || document.querySelector('button[aria-label*="Send"]')
          || document.querySelector('button[aria-label*="send"]');
        if (!btn) { var s = document.querySelector('form button svg'); if (s) btn = s.closest('button'); }
        if (btn && !btn.disabled) { btn.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, cancelable: true, pointerId: 1, pointerType: 'mouse', isPrimary: true })); btn.dispatchEvent(new PointerEvent('pointerup', { bubbles: true, cancelable: true, pointerId: 1, pointerType: 'mouse', isPrimary: true })); btn.click(); }
        else if (sendAttempts < 10) { sendAttempts++; setTimeout(trySend, 200); }
        else if (input) { input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true, cancelable: true })); }
      };
      setTimeout(trySend, 300);

      if (g_timer) clearInterval(g_timer);
      var last = '', stable = 0, start = Date.now();
      g_timer = setInterval(function () {
        var stopBtn = document.querySelector('button[data-testid="stop-button"]') || document.querySelector('button[aria-label*="Stop"]');
        var resp = document.querySelector('div[data-message-author-role="assistant"]:last-of-type');
        var text = resp ? (resp.textContent || resp.innerText || '') : '';
        if (text === last && !stopBtn) stable++; else stable = 0;
        last = text;
        if (stable >= 5 && text.trim()) { clearInterval(g_timer); g_timer = null; chrome.runtime.sendMessage({ action: 'contentScriptStatus', status: 'done', prompt: msg.prompt, text: text, timestamp: Date.now() }, function() {}); }
        if (Date.now() - start > 180000) { clearInterval(g_timer); g_timer = null; chrome.runtime.sendMessage({ action: 'contentScriptStatus', status: 'timeout', prompt: msg.prompt, partialText: text }, function() {}); }
      }, 300);
    }
    if (msg.action === 'cancelGeneration') { if (g_timer) { clearInterval(g_timer); g_timer = null; } var sb = document.querySelector('button[data-testid="stop-button"]'); if (sb) sb.click(); sendResponse({ status: 'cancelled' }); return false; }
    return false;
  });
}

async function onCancel(sr) {
  try {
    var tabs = await chrome.tabs.query({ url: ['https://chatgpt.com/*', 'https://chat.openai.com/*'] });
    if (tabs.length) await chrome.tabs.sendMessage(tabs[0].id, { action: 'cancelGeneration' });
    sr({ status: 'cancelled' });
  } catch (e) { sr({ status: 'error', message: e.message }); }
}

async function onContentStatus(msg) {
  if (msg.status === 'done') {
    broadcast({ action: 'statusUpdate', status: 'forwarding', text: msg.text });
    if (g_auto) {
      try {
        var url = g_webhook || (await chrome.storage.sync.get(K_WEBHOOK))[K_WEBHOOK] || '';
        if (!url) { broadcast({ action: 'statusUpdate', status: 'error', message: 'Webhook not configured' }); return; }

        // Determine if this is a gpt-loop message.
        // gpt-loop messages use sender="gpt_loop" and chat_id="gpt_loop".
        // They must NOT be sent to Feishu directly — only to the Bridge
        // so that the gpt-loop engine can process @MAIN: / ##TASK_DONE##
        // without the raw instruction leaking to the chat.
        //
        // Chrome MV3 terminates idle Service Workers after ~30s.  Restore
        // the prompt→chat_id map from chrome.storage.session so we don't
        // lose it across worker restarts.
        var TTL_MS = 10 * 60 * 1000;  // 10 minutes
        var stored = (await chrome.storage.session.get(['bridgePromptMap', 'bridgeLastSender', 'bridgeLastChatId', 'bridgeLastTs'])) || {};
        var storedMap = stored.bridgePromptMap || {};
        var storedSender = stored.bridgeLastSender || '';
        var storedChatId = stored.bridgeLastChatId || '';
        var storedTs = stored.bridgeLastTs || 0;
        var storageValid = (Date.now() - storedTs) < TTL_MS;

        // Resolve chatId: try stored map first, then in-memory map
        var chatId = (storageValid ? storedMap[msg.prompt] : '') || g_promptChatMap[msg.prompt] || '';
        var effectiveSender = (storageValid ? storedSender : '') || g_lastBridgeSender || '';
        var effectiveChatId = (storageValid ? storedChatId : '') || chatId || '';

        // Loop control markers in the response text itself (fallback when map is lost)
        var hasLoopMarker =
            (msg.text || '').indexOf('@MAIN:') >= 0 ||
            (msg.text || '').indexOf('##TASK_DONE##') >= 0 ||
            (msg.text || '').indexOf('##PROJECT_CLOSED##') >= 0;

        var isLoopMessage =
            chatId === 'gpt_loop' ||
            effectiveChatId === 'gpt_loop' ||
            effectiveSender === 'gpt_loop' ||
            (hasLoopMarker && storageValid && effectiveChatId === 'gpt_loop') ||
            hasLoopMarker;  // Last-resort: text contains @MAIN/TASK_DONE/PROJECT_CLOSED

        if (!isLoopMessage) {
          await chrome.storage.session.set({ bfwd: { p: msg.prompt, r: msg.text, t: Date.now() } });
          await feishuPost(url, buildCard(msg.prompt, msg.text, g_lastBridgeSender));
          await chrome.storage.session.remove('bfwd');
        } else {
          console.log('[bg] Loop message detected — skipping Feishu webhook');
        }

        // Notify Hermes via bridge so 大龙虾 can respond
        // (Always notify Bridge — gpt-loop needs this for @MAIN processing)
        var bridgeChatId = chatId || effectiveChatId || 'gpt_loop';
        if (bridgeChatId) {
          try {
            await fetch(BRIDGE_URL + '/response', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ chat_id: bridgeChatId, text: buildCard(msg.prompt, msg.text, g_lastBridgeSender).content.text })
            });
            delete g_promptChatMap[msg.prompt];  // cleanup in-memory
            // Cleanup persisted map after successful delivery
            chrome.storage.session.remove('bridgePromptMap');
            chrome.storage.session.remove('bridgeLastSender');
            chrome.storage.session.remove('bridgeLastChatId');
            chrome.storage.session.remove('bridgeLastTs');
          } catch (e) { console.log('[bg] Bridge response notify failed:', e.message); }
        }

        broadcast({ action: 'statusUpdate', status: 'done', text: msg.text });
      } catch (e) {
        console.error('[bg] Feishu fail:', e.message);
        broadcast({ action: 'statusUpdate', status: 'error', code: e.message, message: errMsg(e.message) });
      }
    } else { broadcast({ action: 'statusUpdate', status: 'done', text: msg.text }); }
  } else if (msg.status === 'timeout') {
    broadcast({ action: 'statusUpdate', status: 'error', code: 'TIMEOUT', message: 'Response timed out' });
  } else {
    broadcast({ action: 'statusUpdate', status: msg.status, code: msg.code, message: msg.error });
  }
}

async function onTest(url, sr) {
  try {
    await feishuPost(url, { msg_type: 'text', content: { text: 'ChatGPT Feishu Bridge webhook test.' } });
    sr({ status: 'ok' });
  } catch (e) { sr({ status: 'error', message: errMsg(e.message) }); }
}

// ---- Feishu ----
var BOT_OPEN_ID = 'ou_4f9ffa90aa724b44d64e009ea8681c97';   // CY助手 bot

function buildCard(prompt, response, atUser) {
  var r = (response || '').length > 30000 ? response.slice(0, 30000) + '...(truncated)' : (response || '');
  // Strip leading /bridge and @CY助手 prefixes that ChatGPT may add
  r = r.replace(/^\/bridge\s+/i, '');
  r = r.replace(/^@CY助手\s*/i, '');

  // @mention the bot so 大龙虾 responds
  var atMention = '<at user_id="' + BOT_OPEN_ID + '">CY助手</at>';
  var body = atMention + ' ChatGPT 回复：\n' + r + '\n\n---\nChatGPT Feishu Bridge';

  return {
    msg_type: 'text',
    content: { text: body }
  };
}

// ---- Bridge Polling (local HTTP bridge for Feishu → ChatGPT) ----
var BRIDGE_URL = 'http://127.0.0.1:18640';
var g_lastBridgeSender = '';
var g_promptChatMap = {};  // prompt text → chat_id

chrome.alarms.create('bridgePoll', { periodInMinutes: 1 });
chrome.alarms.onAlarm.addListener(function (alarm) {
  if (alarm.name === 'bridgePoll') pollBridge();
});

async function pollBridge() {
  try {
    var resp = await fetch(BRIDGE_URL + '/pending');
    if (!resp.ok) return;
    var data = await resp.json();
    var msgs = data.messages || [];
    if (!msgs.length) return;

    console.log('[bg] Bridge: ' + msgs.length + ' pending message(s)');

    var ackedIds = [];
    for (var i = 0; i < msgs.length; i++) {
      var msg = msgs[i];
      var text = (msg.text || '').trim();
      if (!text) { ackedIds.push(msg._id); continue; }  // ACK empty messages to clear them
      console.log('[bg] Bridge msg ' + (msg._id || '?') + ' from ' + (msg.sender || '?') + ': ' + text.slice(0, 60));

      // Store sender and chat_id for response routing
      g_lastBridgeSender = msg.sender || '';
      if (msg.chat_id) {
        g_promptChatMap[text] = msg.chat_id;
      }

      // Persist to session storage so state survives Service Worker restarts.
      chrome.storage.session.set({
        bridgePromptMap: g_promptChatMap,
        bridgeLastSender: msg.sender || '',
        bridgeLastChatId: msg.chat_id || '',
        bridgeLastTs: Date.now()
      });

      // Forward to ChatGPT
      try {
        await forwardToChatGPT(text);
        ackedIds.push(msg._id);  // ACK on success
      } catch (e) {
        console.log('[bg] Forward failed for ' + msg._id + ': ' + e.message);
        // Leave un-ACKed so it can be retried next poll
      }
    }

    // ACK processed messages
    if (ackedIds.length > 0) {
      await fetch(BRIDGE_URL + '/pending/ack', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ids: ackedIds })
      }).catch(function () {});
    }
  } catch (e) {
    // Bridge not running — silent
  }
}

async function forwardToChatGPT(text) {
  try {
    var tabs = await chrome.tabs.query({ url: ['https://chatgpt.com/*', 'https://chat.openai.com/*'] });
    if (!tabs.length) { console.log('[bg] No ChatGPT tab for bridge msg'); return; }
    var tabId = tabs[0].id;

    // Ensure content script loaded
    var csOk = false;
    try { var p = await chrome.tabs.sendMessage(tabId, { action: 'ping' }); csOk = !!(p && p.loggedIn); } catch (_) {}
    if (!csOk) {
      try { await chrome.scripting.executeScript({ target: { tabId: tabId }, files: ['src/content.js'] }); await new Promise(function (r) { setTimeout(r, 300); }); } catch (_) {}
      try { await chrome.scripting.executeScript({ target: { tabId: tabId }, func: injectedContentScript }); await new Promise(function (r) { setTimeout(r, 500); }); } catch (_) {}
    }

    await chrome.tabs.sendMessage(tabId, { action: 'sendPrompt', prompt: text });
    console.log('[bg] Bridge prompt sent to ChatGPT');
  } catch (e) { console.log('[bg] Bridge forward error:', e.message); }
}

async function feishuPost(url, payload) {
  if (!url) throw new Error('NO_URL');
  var ctrl = new AbortController();
  var timer = setTimeout(function () { ctrl.abort(); }, 10000);
  try {
    var resp = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal: ctrl.signal });
    clearTimeout(timer);
    if (!resp.ok) { var txt = ''; try { txt = await resp.text(); } catch (_) {} throw new Error('HTTP_' + resp.status + ': ' + txt.slice(0, 150)); }
    return await resp.json();
  } catch (e) { clearTimeout(timer); if (e.name === 'AbortError') throw new Error('TIMEOUT'); throw e; }
}

function errMsg(code) {
  if (!code) return 'Unknown error';
  if (code === 'NO_URL') return 'Webhook URL not configured. Open Settings.';
  if (code === 'TIMEOUT') return 'Feishu request timed out.';
  if (code.indexOf('HTTP_401') >= 0 || code.indexOf('HTTP_403') >= 0) return 'Invalid webhook token.';
  if (code.indexOf('HTTP_') >= 0) return 'Feishu error: ' + code;
  return code;
}
