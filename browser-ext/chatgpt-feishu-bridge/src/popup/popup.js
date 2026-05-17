// popup.js — Popup UI with 5-state machine
(function () {
  'use strict';

  const Cfg = window.BridgeConfig;

  const STATES = {
    IDLE: 'idle',
    SENDING: 'sending',
    WAITING: 'waiting',
    DONE: 'done',
    ERROR: 'error',
    FORWARDING: 'forwarding'
  };

  let currentState = STATES.IDLE;
  let port = null;

  // DOM
  const $ = (sel) => document.querySelector(sel);

  function cacheDom() {
    return {
      statusBar: $('#status-bar'),
      statusText: $('#status-text'),
      statusDot: $('#status-dot'),
      promptInput: $('#prompt-input'),
      sendBtn: $('#send-btn'),
      cancelBtn: $('#cancel-btn'),
      resultSection: $('#result-section'),
      responsePreview: $('#response-preview'),
      errorSection: $('#error-section'),
      errorMessage: $('#error-message'),
      autoSendToggle: $('#auto-send-toggle'),
      settingsLink: $('#settings-link')
    };
  }

  let dom;

  // ---- INIT ----
  function init() {
    dom = cacheDom();
    loadConfig();
    connectPort();
    bindEvents();
    restoreState();
    checkChatGPTTab();
  }

  async function loadConfig() {
    try {
      const cfg = await Cfg.loadAll();
      dom.autoSendToggle.checked = cfg[Cfg.CONFIG_KEYS.AUTO_SEND_ENABLED] !== false;
    } catch (e) {
      // defaults
    }
  }

  function connectPort() {
    try {
      port = chrome.runtime.connect({ name: 'popup' });
      port.onMessage.addListener(handlePortMessage);
      port.onDisconnect.addListener(() => {
        port = null;
        setState(STATES.ERROR, { message: 'Service worker disconnected. Reopen popup.' });
      });
    } catch (e) {
      setState(STATES.ERROR, { message: 'Cannot connect to extension. Try reloading.' });
    }
  }

  function bindEvents() {
    dom.sendBtn.addEventListener('click', onSend);
    dom.cancelBtn.addEventListener('click', onCancel);
    dom.settingsLink.addEventListener('click', (e) => {
      e.preventDefault();
      chrome.runtime.sendMessage({ action: 'openOptions' });
    });
    dom.autoSendToggle.addEventListener('change', (e) => {
      Cfg.set(Cfg.CONFIG_KEYS.AUTO_SEND_ENABLED, e.target.checked);
    });

    // Enter key to send (Shift+Enter for newline)
    dom.promptInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        onSend();
      }
    });
  }

  async function restoreState() {
    try {
      const stored = await chrome.storage.session.get('lastPopupState');
      const state = stored.lastPopupState;
      if (state && state.timestamp && (Date.now() - state.timestamp < 60000)) {
        if (state.state === STATES.DONE && state.lastResponse) {
          setState(STATES.DONE, { text: state.lastResponse });
        }
      }
    } catch (e) { /* ignore */ }
  }

  async function checkChatGPTTab() {
    try {
      chrome.runtime.sendMessage({ action: 'checkStatus' }, (resp) => {
        if (chrome.runtime.lastError) return;
        if (resp && !resp.hasActiveTab) {
          setState(STATES.ERROR, { message: 'No ChatGPT tab found. Open chatgpt.com first.' });
        }
      });
    } catch (e) { /* ignore */ }
  }

  // ---- STATE MACHINE ----
  function setState(newState, data = {}) {
    currentState = newState;
    const s = dom;

    // Status bar
    s.statusBar.className = 'status-' + newState;
    s.statusDot.className = 'status-dot-' + newState;

    const stateLabels = {
      idle: 'Ready',
      sending: 'Sending to ChatGPT...',
      waiting: 'Waiting for response...',
      forwarding: 'Forwarding to Feishu...',
      done: 'Sent to Feishu',
      error: 'Error'
    };
    s.statusText.textContent = data.message || stateLabels[newState] || newState;

    // Buttons
    const busy = (newState === STATES.SENDING || newState === STATES.WAITING || newState === STATES.FORWARDING);
    s.sendBtn.classList.toggle('hidden', busy);
    s.cancelBtn.classList.toggle('hidden', !busy);
    s.promptInput.disabled = busy;

    // Result
    if (newState === STATES.DONE && data.text) {
      showResult(data.text);
    } else if (newState !== STATES.DONE) {
      s.resultSection.classList.add('hidden');
    }

    // Error
    if (newState === STATES.ERROR) {
      s.errorSection.classList.remove('hidden');
      s.errorMessage.textContent = data.message || 'Unknown error';
    } else {
      s.errorSection.classList.add('hidden');
    }

    // Persist
    chrome.storage.session.set({
      lastPopupState: {
        state: newState,
        message: data.message || null,
        lastResponse: data.text || null,
        timestamp: Date.now()
      }
    }).catch(() => {});
  }

  function showResult(text) {
    dom.resultSection.classList.remove('hidden');
    dom.responsePreview.textContent = text;
  }

  // ---- HANDLERS ----
  async function onSend() {
    const prompt = dom.promptInput.value.trim();
    if (!prompt) return;

    setState(STATES.SENDING);
    savePendingPrompt(prompt);

    try {
      chrome.runtime.sendMessage({ action: 'sendPrompt', prompt }, (resp) => {
        if (chrome.runtime.lastError) {
          setState(STATES.ERROR, { message: 'Send failed: ' + chrome.runtime.lastError.message });
          return;
        }
        if (resp && resp.status === 'accepted') {
          setState(STATES.WAITING);
        } else if (resp) {
          setState(STATES.ERROR, { message: resp.message || resp.code || 'Unknown error' });
        }
      });
    } catch (e) {
      setState(STATES.ERROR, { message: 'Send error: ' + e.message });
    }
  }

  function onCancel() {
    chrome.runtime.sendMessage({ action: 'cancelGeneration' }, () => {
      setState(STATES.IDLE);
    });
  }

  function handlePortMessage(msg) {
    switch (msg.action) {
      case 'statusUpdate':
        switch (msg.status) {
          case 'sending': setState(STATES.SENDING); break;
          case 'waiting': setState(STATES.WAITING); break;
          case 'forwarding': setState(STATES.FORWARDING); break;
          case 'done': setState(STATES.DONE, { text: msg.text }); break;
          case 'error': setState(STATES.ERROR, { message: msg.message || msg.code }); break;
          case 'generating': setState(STATES.WAITING); break;
          default: break;
        }
        break;
      case 'responseComplete':
        setState(STATES.DONE, { text: msg.text });
        break;
      case 'error':
        setState(STATES.ERROR, { message: msg.message || msg.code });
        break;
    }
  }

  async function savePendingPrompt(prompt) {
    try {
      await chrome.storage.session.set({
        pendingPopupPrompt: { prompt, timestamp: Date.now() }
      });
    } catch (e) { /* ignore */ }
  }

  // ---- STARTUP ----
  document.addEventListener('DOMContentLoaded', init);
})();
