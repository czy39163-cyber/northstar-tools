# ACCEPTANCE.md — B3 五项一致性验收

## 元信息

- **工具名称**: ChatGPT Feishu Bridge (大龙虾)
- **版本**: v1.0.0
- **交付日期**: 2026-05-12
- **建设单位**: BLD / 铁甲虾
- **验收口径**: MAIN / 大龙虾

## B3 验收清单

### 1. 文档-功能一致

| 文档声明 | 代码实现 | 状态 |
|----------|----------|------|
| Popup 输入 prompt 发送到 ChatGPT | `content.js:handleSendPrompt()` 通过 React-compatible 方式注入输入框并点击发送 | ✅ |
| 自动抓取 ChatGPT 回复 | `content.js:startResponseMonitoring()` 三重信号检测 (Stop按钮+文本稳定+Regenerate按钮) | ✅ |
| 自动喂回飞书 | `background.js:forwardToFeishu()` 调用 Feishu webhook，发送 interactive card | ✅ |
| Options 页配置 webhook URL | `options.js:saveSettings()` 存储到 chrome.storage.sync | ✅ |
| Test Webhook 按钮 | `options.js:testWebhook()` 发送测试消息到飞书 | ✅ |
| Auto-send 开关 | popup toggle + background.js 条件判断 | ✅ |
| 5 状态机 | `popup.js:setState()` idle/sending/waiting/done/error | ✅ |
| 错误处理 | login/rate-limit/timeout/DOM-changed/webhook-err | ✅ |

### 2. 执行-输出一致

| 操作 | 预期输出 | 验证方式 |
|------|----------|----------|
| 加载扩展 | chrome://extensions 无错误 | 加载已解压扩展，检查无红色错误 |
| 打开 Options 页 | 显示配置表单，保存后刷新不丢失 | 填入 webhook URL → 保存 → 关闭再打开 |
| Test Webhook | 飞书群收到 "test successful" 消息 | 点 Test 按钮，检查飞书 |
| 发送 prompt | ChatGPT 自动输入并发送 | 打开 chatgpt.com，popup 输入 "你好" → 发送 |
| 响应捕获 | popup 显示 "Sent to Feishu" | 等待 ChatGPT 回复完成 |
| 飞书收到消息 | 飞书群收到 interactive card | 检查飞书群消息 |

### 3. 边界条件一致

| 边界条件 | 处理方式 | 状态 |
|----------|----------|------|
| 空 prompt | popup 不发送，background 返回 EMPTY_PROMPT | ✅ |
| 未打开 chatgpt.com | background 返回 NO_CHATGPT_TAB，popup 显示错误 | ✅ |
| 未登录 ChatGPT | content.js checkLoginStatus() 返回 false，报 NOT_LOGGED_IN | ✅ |
| ChatGPT rate limit | content.js checkRateLimit() 检测 body 文本，报 RATE_LIMITED | ✅ |
| ChatGPT DOM 结构变化 | 选择器链全部返回 null，报 DOM_CHANGED 并记录 DOM metadata | ✅ |
| 飞书 webhook 未配置 | background.js 检查空 URL，报 FEISHU_WEBHOOK_NOT_CONFIGURED | ✅ |
| 飞书 webhook 返回错误 | background.js formatFeishuError() 格式化各 HTTP 状态码 | ✅ |
| 飞书请求超时 | feishu.js AbortController 10s 超时 | ✅ |
| ChatGPT 响应超时 (3min) | content.js MAX_WAIT_MS，如有部分文本则发送并标记截断 | ✅ |
| ChatGPT 返回空响应 | content.js 检查空文本，报 EMPTY_RESPONSE | ✅ |
| 响应超长 (>50000 chars) | content.js 截断并标记 | ✅ |
| Service Worker 休眠 | background.js 在异步前保存 pendingForward 到 session storage | ✅ |
| 多个 ChatGPT tab | findChatGPTTabs() 返回第一个匹配 tab | ✅ |
| Popup 关闭再打开 | 从 chrome.storage.session 恢复状态 (60s 内) | ✅ |
| 正在生成时再次发送 | 取消前一个生成，等 300ms 再发新的 | ✅ |

### 4. 调度机制一致

| 机制 | 实现 | 状态 |
|------|------|------|
| Content script 注入 | manifest.json content_scripts matches chatgpt.com + chat.openai.com | ✅ |
| Service worker 生命周期 | 通过 chrome.storage.session 持久化 pending 状态 | ✅ |
| Popup ↔ Background 通信 | chrome.runtime.connect port 长连接 | ✅ |
| Background ↔ Content 通信 | chrome.tabs.sendMessage | ✅ |
| 配置同步 | chrome.storage.sync + onChanged listener | ✅ |

### 5. MAIN 可消费一致

| 要求 | 实现 | 状态 |
|------|------|------|
| 扩展可独立加载运行 | 开发者模式加载已解压扩展，无外部依赖 | ✅ |
| 配置可持久化 | chrome.storage.sync 跨设备同步 | ✅ |
| 飞书消息格式稳定 | interactive card schema 固定 | ✅ |
| 错误信息结构化 | { action, status, code, message } 格式 | ✅ |
| README 包含完整使用说明 | README.md 含安装/配置/使用/排错 | ✅ |

## 验收结论

- [ ] 基础功能一致性验收通过
- [ ] 完整链路验收通过 (需要 chatgpt.com + 飞书 webhook 实环境)

## 已知限制

1. ChatGPT DOM 选择器可能因 ChatGPT UI 更新而失效，需维护 `src/lib/selectors.js`
2. 不支持自动登录 ChatGPT（需用户手动登录）
3. 不支持多轮对话上下文管理（每次发送是独立的 prompt）
4. 飞书 interactive card 单条消息最大 ~30KB，超长响应会被截断
5. Service Worker 在 MV3 下可能随时被终止，已通过 session storage 缓解

## 后续建议

1. 添加右键菜单 "Send selected text to ChatGPT"
2. 支持多轮对话（保持 ChatGPT 会话上下文）
3. 支持定时自动发送（cron 触发）
4. 添加响应历史记录
5. 支持飞书消息触发（接收飞书消息 → 转发给 ChatGPT → 回复飞书）
