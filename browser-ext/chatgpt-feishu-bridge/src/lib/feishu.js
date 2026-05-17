// feishu.js — Feishu webhook payload builder and sender
(function () {
  'use strict';

  var FEISHU_MAX_TEXT = 30000;
  var FEISHU_TIMEOUT_MS = 10000;

  function truncate(text, maxLen) {
    if (!text || text.length <= maxLen) return text || '';
    return text.slice(0, maxLen) + '\n\n...(truncated)';
  }

  function buildInteractiveCard(promptText, responseText, metadata) {
    var safePrompt = truncate(promptText, 2000);
    var safeResponse = truncate(responseText, FEISHU_MAX_TEXT);
    var ts = (metadata && metadata.timestamp)
      ? new Date(metadata.timestamp).toLocaleString()
      : new Date().toLocaleString();

    var body = '**Prompt:**\n' + safePrompt + '\n\n**Response:**\n' + safeResponse;

    return {
      msg_type: 'interactive',
      card: {
        config: { wide_screen_mode: true, enable_forward: true },
        header: {
          title: { tag: 'plain_text', content: 'ChatGPT Response' },
          template: 'blue'
        },
        elements: [
          { tag: 'markdown', content: body },
          { tag: 'hr' },
          { tag: 'note', elements: [{ tag: 'plain_text', content: 'Sent by ChatGPT Feishu Bridge -- ' + ts }] }
        ]
      }
    };
  }

  function buildTextCard(promptText, responseText) {
    var body = 'Prompt:\n' + truncate(promptText, 1000) + '\n\nResponse:\n' + truncate(responseText, FEISHU_MAX_TEXT);
    return { msg_type: 'text', content: { text: body } };
  }

  function buildErrorCard(errorMsg) {
    return {
      msg_type: 'interactive',
      card: {
        config: { wide_screen_mode: true },
        header: {
          title: { tag: 'plain_text', content: 'ChatGPT Bridge Error' },
          template: 'red'
        },
        elements: [
          { tag: 'markdown', content: '**Error:**\n' + errorMsg },
          { tag: 'hr' },
          { tag: 'note', elements: [{ tag: 'plain_text', content: 'Sent by ChatGPT Feishu Bridge -- ' + new Date().toLocaleString() }] }
        ]
      }
    };
  }

  function buildTestCard() {
    return { msg_type: 'text', content: { text: 'ChatGPT Feishu Bridge webhook test successful.' } };
  }

  async function send(webhookUrl, payload) {
    if (!webhookUrl) throw new Error('FEISHU_WEBHOOK_NOT_CONFIGURED');

    var controller = new AbortController();
    var timer = setTimeout(function () { controller.abort(); }, FEISHU_TIMEOUT_MS);

    try {
      var response = await fetch(webhookUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: controller.signal
      });
      clearTimeout(timer);

      if (!response.ok) {
        var errBody = '';
        try { errBody = await response.text(); } catch (_) { errBody = '(no body)'; }
        throw new Error('FEISHU_HTTP_' + response.status + ': ' + errBody.slice(0, 200));
      }

      return await response.json();
    } catch (e) {
      clearTimeout(timer);
      if (e.name === 'AbortError') throw new Error('FEISHU_TIMEOUT');
      throw e;
    }
  }

  var api = {
    FEISHU_MAX_TEXT: FEISHU_MAX_TEXT,
    truncate: truncate,
    buildInteractiveCard: buildInteractiveCard,
    buildTextCard: buildTextCard,
    buildErrorCard: buildErrorCard,
    buildTestCard: buildTestCard,
    send: send
  };

  var root = typeof window !== 'undefined' ? window : self;
  root.BridgeFeishu = api;
})();
