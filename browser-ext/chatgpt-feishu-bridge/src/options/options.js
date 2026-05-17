// options.js — Settings page logic
(function () {
  'use strict';

  var Cfg = window.BridgeConfig;
  var Feishu = window.BridgeFeishu;

  var els = {};
  function cacheDom() {
    els.webhook = document.getElementById('feishu-webhook');
    els.autoSend = document.getElementById('auto-send');
    els.promptPrefix = document.getElementById('prompt-prefix');
    els.maxLength = document.getElementById('max-length');
    els.testBtn = document.getElementById('test-webhook-btn');
    els.webhookStatus = document.getElementById('webhook-status');
    els.saveBtn = document.getElementById('save-btn');
    els.resetBtn = document.getElementById('reset-btn');
    els.saveStatus = document.getElementById('save-status');
  }

  async function loadSettings() {
    try {
      var cfg = await Cfg.loadAll();
      els.webhook.value = cfg[Cfg.CONFIG_KEYS.FEISHU_WEBHOOK_URL] || '';
      els.autoSend.checked = cfg[Cfg.CONFIG_KEYS.AUTO_SEND_ENABLED] !== false;
      els.promptPrefix.value = cfg[Cfg.CONFIG_KEYS.PROMPT_PREFIX] || '';
      els.maxLength.value = cfg[Cfg.CONFIG_KEYS.MAX_RESPONSE_LENGTH] || 50000;
    } catch (e) {
      showSaveStatus('Failed to load settings: ' + e.message, 'error');
    }
  }

  async function saveSettings() {
    try {
      await Cfg.set(Cfg.CONFIG_KEYS.FEISHU_WEBHOOK_URL, els.webhook.value.trim());
      await Cfg.set(Cfg.CONFIG_KEYS.AUTO_SEND_ENABLED, els.autoSend.checked);
      await Cfg.set(Cfg.CONFIG_KEYS.PROMPT_PREFIX, els.promptPrefix.value);
      var maxLen = parseInt(els.maxLength.value, 10) || 50000;
      await Cfg.set(Cfg.CONFIG_KEYS.MAX_RESPONSE_LENGTH, Math.max(1000, Math.min(100000, maxLen)));
      showSaveStatus('Settings saved.', 'ok');
    } catch (e) {
      showSaveStatus('Save failed: ' + e.message, 'error');
    }
  }

  async function resetSettings() {
    var defs = Cfg.getDefaults();
    els.webhook.value = defs[Cfg.CONFIG_KEYS.FEISHU_WEBHOOK_URL];
    els.autoSend.checked = defs[Cfg.CONFIG_KEYS.AUTO_SEND_ENABLED];
    els.promptPrefix.value = defs[Cfg.CONFIG_KEYS.PROMPT_PREFIX];
    els.maxLength.value = defs[Cfg.CONFIG_KEYS.MAX_RESPONSE_LENGTH];
    await saveSettings();
  }

  async function testWebhook() {
    var url = els.webhook.value.trim();
    if (!url) {
      showWebhookStatus('Please enter a webhook URL first.', 'error');
      return;
    }
    showWebhookStatus('Testing...', 'testing');
    try {
      await Feishu.send(url, Feishu.buildTestCard());
      showWebhookStatus('Connected — check Feishu for test message.', 'ok');
    } catch (e) {
      showWebhookStatus(formatError(e.message), 'error');
    }
  }

  function showWebhookStatus(msg, type) {
    els.webhookStatus.textContent = msg;
    els.webhookStatus.className = 'status-indicator status-' + type;
  }

  function showSaveStatus(msg, type) {
    els.saveStatus.textContent = msg;
    els.saveStatus.className = 'status-indicator status-' + type;
    if (type === 'ok') {
      setTimeout(function () { els.saveStatus.textContent = ''; }, 3000);
    }
  }

  function formatError(code) {
    if (code === 'FEISHU_WEBHOOK_NOT_CONFIGURED') return 'No webhook URL configured.';
    if (code === 'FEISHU_TIMEOUT') return 'Request timed out.';
    if (code.indexOf('FEISHU_HTTP_401') >= 0 || code.indexOf('FEISHU_HTTP_403') >= 0)
      return 'Invalid webhook token.';
    if (code.indexOf('FEISHU_HTTP_') >= 0) return 'HTTP error: ' + code;
    return code;
  }

  function init() {
    cacheDom();
    loadSettings();
    els.saveBtn.addEventListener('click', saveSettings);
    els.resetBtn.addEventListener('click', resetSettings);
    els.testBtn.addEventListener('click', testWebhook);
  }

  document.addEventListener('DOMContentLoaded', init);
})();
