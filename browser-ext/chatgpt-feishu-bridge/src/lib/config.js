// config.js — chrome.storage wrapper
// Works in: content script (window), popup (window), service worker (self)

(function () {
  'use strict';

  var CONFIG_KEYS = {
    FEISHU_WEBHOOK_URL: 'feishuWebhookUrl',
    AUTO_SEND_ENABLED: 'autoSendEnabled',
    PROMPT_PREFIX: 'promptPrefix',
    MAX_RESPONSE_LENGTH: 'maxResponseLength',
    LAST_SESSION_STATE: 'lastSessionState'
  };

  var DEFAULTS = {
    feishuWebhookUrl: '',
    autoSendEnabled: true,
    promptPrefix: '',
    maxResponseLength: 50000,
    lastSessionState: null
  };
  // Map computed keys to DEFAULTS
  DEFAULTS[CONFIG_KEYS.FEISHU_WEBHOOK_URL] = '';
  DEFAULTS[CONFIG_KEYS.AUTO_SEND_ENABLED] = true;
  DEFAULTS[CONFIG_KEYS.PROMPT_PREFIX] = '';
  DEFAULTS[CONFIG_KEYS.MAX_RESPONSE_LENGTH] = 50000;
  DEFAULTS[CONFIG_KEYS.LAST_SESSION_STATE] = null;

  var _cache = null;

  async function loadAll() {
    var result = await chrome.storage.sync.get(DEFAULTS);
    _cache = result;
    return result;
  }

  async function get(key) {
    if (_cache && key in _cache) return _cache[key];
    var result = await chrome.storage.sync.get(key);
    if (_cache) _cache[key] = result[key];
    return result[key] != null ? result[key] : DEFAULTS[key];
  }

  async function set(key, value) {
    var obj = {};
    obj[key] = value;
    await chrome.storage.sync.set(obj);
    if (_cache) _cache[key] = value;
  }

  function getCached(key) {
    if (_cache && key in _cache) return _cache[key];
    return DEFAULTS[key];
  }

  function getDefaults() {
    return JSON.parse(JSON.stringify(DEFAULTS));
  }

  var api = {
    CONFIG_KEYS: CONFIG_KEYS, DEFAULTS: DEFAULTS,
    loadAll: loadAll, get: get, set: set,
    getCached: getCached, getDefaults: getDefaults
  };

  var root = typeof window !== 'undefined' ? window : self;
  root.BridgeConfig = api;
})();
