// content.js — ChatGPT DOM interaction
if (window.__BRIDGE_INJECTED) { console.log('[BRIDGE] Already injected'); }
else { window.__BRIDGE_INJECTED = true;
console.log('[BRIDGE] Content script loaded on ' + window.location.href);

var g_timer = null;
var g_preSendLastText = '';  // text of last assistant BEFORE sending prompt

// Safe wrapper — chrome.runtime may be undefined in non-extension contexts
function safeSend(msg) {
  if (typeof chrome === 'undefined' || !chrome.runtime) {
    console.log('[BRIDGE] chrome.runtime unavailable, cannot send:', msg.status);
    return;
  }
  chrome.runtime.sendMessage(msg, function() {});
}

chrome.runtime.onMessage.addListener(function (msg, sender, sendResponse) {
  if (msg.action === 'ping') { sendResponse({ status: 'alive', loggedIn: true }); return true; }
  if (msg.action === 'sendPrompt') { sendResponse({ status: 'accepted' }); injectAndSend(msg.prompt); return false; }
  if (msg.action === 'cancelGeneration') { cancelGen(); sendResponse({ status: 'cancelled' }); return false; }
  return false;
});

function getLastAsstText() {
  var all = document.querySelectorAll('div[data-message-author-role="assistant"]');
  if (all.length === 0) return '';
  var last = all[all.length - 1];
  var content = last.querySelector('div.markdown') || last.querySelector('div[class*="markdown"]') || last;
  return (content.textContent || content.innerText || '').trim();
}

function getLastAsstCount() {
  return document.querySelectorAll('div[data-message-author-role="assistant"]').length;
}

function injectAndSend(prompt) {
  var input = document.querySelector('#prompt-textarea')
    || document.querySelector('form textarea')
    || document.querySelector('div[contenteditable="true"]')
    || document.querySelector('[role="textbox"]');

  if (!input) {
    safeSend({ action: 'contentScriptStatus', status: 'error', code: 'NO_INPUT' });
    return;
  }

  // CAPTURE current state BEFORE sending (this is the key fix)
  g_preSendLastText = getLastAsstText();
  var preSendCount = getLastAsstCount();
  console.log('[BRIDGE] Pre-send: asst count=' + preSendCount + ', last text=' + g_preSendLastText.slice(0, 60));

  // Character-by-character with realistic delays — ChatGPT detects zero-gap events.
  // Type first 80 chars with per-char delays, then paste remainder.
  if (input.tagName === 'TEXTAREA' || input.tagName === 'INPUT') {
    var proto = input.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    var desc = Object.getOwnPropertyDescriptor(proto, 'value');
    var setter = (desc && desc.set) ? desc.set : null;
    if (setter) {
      setter.call(input, '');
      var SIMULATE = 80;
      var DELAY = 35;
      var head = prompt.slice(0, SIMULATE);
      var tail = prompt.slice(SIMULATE);
      var idx = 0;
      var typeNext = function() {
        if (idx < head.length) {
          setter.call(input, input.value + head[idx]);
          input.dispatchEvent(new InputEvent('input', { data: head[idx], inputType: 'insertText', bubbles: true, composed: true }));
          idx++;
          setTimeout(typeNext, DELAY);
        } else {
          if (tail) {
            setter.call(input, input.value + tail);
            input.dispatchEvent(new InputEvent('input', { data: tail, inputType: 'insertText', bubbles: true, composed: true }));
          }
          // Typing done — trigger send
          setTimeout(trySend, 300);
        }
      };
      typeNext();
    } else {
      input.value = prompt;
      input.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
    }
  } else {
    input.focus(); input.textContent = prompt;
    input.dispatchEvent(new InputEvent('input', { bubbles: true, composed: true }));
  }

  cancelGen();

  // Click send — poll for button until it renders (React may defer it)
  var sendAttempts = 0;
  var trySend = function () {
    var btn = document.querySelector('#composer-submit-button')
      || document.querySelector('button[data-testid="send-button"]')
      || document.querySelector('button[aria-label*="发送"]')
      || document.querySelector('button[aria-label*="Send"]')
      || document.querySelector('button[aria-label*="send"]');
    if (!btn) {
      var s = (input.closest('form') || document).querySelector('button svg');
      if (s) btn = s.closest('button');
    }
    if (btn && !btn.disabled) {
      btn.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, cancelable: true, pointerId: 1, pointerType: 'mouse', isPrimary: true }));
      btn.dispatchEvent(new PointerEvent('pointerup', { bubbles: true, cancelable: true, pointerId: 1, pointerType: 'mouse', isPrimary: true }));
      btn.click();
    } else if (sendAttempts < 10) {
      sendAttempts++;
      setTimeout(trySend, 200);
    } else if (input) {
      input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true, cancelable: true }));
    }
  };
  // trySend will be started from typeNext after typing completes

  // Start monitoring AFTER send (wait for new response to appear)
  setTimeout(function () { startMonitor(prompt, preSendCount); }, 2000);
}

function startMonitor(prompt, preSendCount) {
  cancelGen();
  var started = Date.now();
  var maxWait = 300000;
  var minLen = 5;
  var lastText = '';
  var stable = 0;
  var gotNew = false;

  g_timer = setInterval(function () {
    var stopBtn = document.querySelector('button[data-testid="stop-button"]') || document.querySelector('button[aria-label*="Stop"]');
    var allAsst = document.querySelectorAll('div[data-message-author-role="assistant"]');
    var curText = '';

    if (allAsst.length > 0) {
      var lastAsst = allAsst[allAsst.length - 1];
      var contentEl = lastAsst.querySelector('div.markdown') || lastAsst.querySelector('div[class*="markdown"]') || lastAsst;
      curText = (contentEl.textContent || contentEl.innerText || '').trim();
    }

    // KEY CHECK: is this text DIFFERENT from what was there before we sent?
    var isNewContent = (curText !== g_preSendLastText);
    // Also check: has a NEW assistant div appeared?
    var hasNewDiv = (allAsst.length > preSendCount);

    if ((isNewContent || hasNewDiv) && curText.length >= minLen && !gotNew) {
      gotNew = true;
      console.log('[BRIDGE] New response detected, length=' + curText.length);
    }

    if (!gotNew) {
      if (Date.now() - started > 120000) {
        clearInterval(g_timer); g_timer = null;
        safeSend({
          action: 'contentScriptStatus', status: 'timeout',
          prompt: prompt, code: 'NO_NEW_CONTENT',
          error: 'No new response detected within 120s'
        });
      }
      return;
    }

    // Stability tracking
    if (curText !== lastText) stable = 0;
    else if (!stopBtn) stable++;
    lastText = curText;

    // Done: stable, has content, is new, stop button gone
    if (stable >= 5 && curText.length >= minLen && !stopBtn) {
      clearInterval(g_timer); g_timer = null;
      console.log('[BRIDGE] Response done, length=' + curText.length);
      safeSend({
        action: 'contentScriptStatus', status: 'done',
        prompt: prompt, text: curText, timestamp: Date.now()
      });
    }

    if (Date.now() - started > maxWait) {
      clearInterval(g_timer); g_timer = null;
      safeSend({
        action: 'contentScriptStatus', status: 'timeout',
        prompt: prompt, partialText: curText
      });
    }
  }, 300);
}

function cancelGen() {
  if (g_timer) { clearInterval(g_timer); g_timer = null; }
  var sb = document.querySelector('button[data-testid="stop-button"]');
  if (sb) sb.click();
}

} // end guard
