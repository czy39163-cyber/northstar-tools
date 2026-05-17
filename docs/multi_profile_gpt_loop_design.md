# 多 Profile GPT-Loop 方案设计

**日期**: 2026-05-16  
**设计者**: BLD / 铁甲虾  
**状态**: 设计阶段，待 CY 审批后施工  

---

## 1. 现状与端口冲突

### 1.1 当前 Profile API 端口

| Profile | API Port | API Key | 状态 |
|---------|----------|---------|------|
| MAIN | 18642 | `main-secret` | ✅ 运行中 |
| DSG | 18645 | `dsg-local-dev` | ✅ 运行中 |
| OPS | 18643 | `ops-local-dev` | ⚠️ 与 Bridge 端口冲突 |
| SALES | 18647 | `hermes-sales-2026-...` | ✅ 运行中 |

### 1.2 冲突处理

OPS API 与 Bridge Server 共用 18643 端口。**Bridge 迁移到 18640**，释放 18643 给 OPS。

---

## 2. 多标签页架构

用户方案：每个 Profile 独占一个 ChatGPT 标签页，避免单标签排队延迟。

```
┌──────────────────────────────────────────────────────────────┐
│                     Chrome 浏览器                              │
│                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │ MAIN Tab │  │ DSG Tab  │  │ OPS Tab  │  │SALES Tab │    │
│  │chatgpt.. │  │chatgpt.. │  │chatgpt.. │  │chatgpt.. │    │
│  │ ──────── │  │ ──────── │  │ ──────── │  │ ──────── │    │
│  │ content  │  │ content  │  │ content  │  │ content  │    │
│  │ .js      │  │ .js      │  │ .js      │  │ .js      │    │
│  │ profile= │  │ profile= │  │ profile= │  │ profile= │    │
│  │  main    │  │   dsg    │  │   ops    │  │  sales   │    │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘    │
│       │              │              │              │          │
│       └──────────────┴──────┬───────┴──────────────┘          │
│                             │                                 │
│                    background.js                               │
│              (路由消息到对应标签页)                              │
└─────────────────────────────┬─────────────────────────────────┘
                              │
                    Bridge Server (18640)
                    ┌─────────┴─────────┐
                    │   PendingStore    │  (共享队列，tag 路由)
                    │   ┌───┬───┬───┐   │
                    │   │ M │ D │ O │ S │  tag → profile
                    │   └───┴───┴───┘   │
                    └─────────┬─────────┘
                              │
          ┌───────────────────┼───────────────────┐
          │                   │                   │
     MAIN API             DSG API            SALES API
     18642                18645               18647
```

### 2.1 标签页管理策略

| 事项 | 方案 |
|------|------|
| 标签页分配 | 每个 profile 1 个固定标签页，首次使用时由扩展自动打开 |
| 标签页识别 | Content script 注入 `window.__BRIDGE_PROFILE = 'main'` |
| 标签页失效 | 用户关闭标签页后，扩展下次轮询时自动重建 |
| 上下文清理 | 每个 profile 独立触发 `/clear` 或刷新标签页 |
| 并发处理 | 各标签页独立，互不阻塞 |

### 2.2 标签页路由流程

```
Bridge GET /pending → [{text, sender, chat_id, _id}]
                         │
                         ▼
              background.js pollBridge()
                         │
              ┌──────────┴──────────┐
              │ chat_id → profile   │  (查路由表)
              │ oc_xxx_main  → main │
              │ oc_xxx_dsg   → dsg  │
              │ oc_xxx_ops   → ops  │
              └──────────┬──────────┘
                         │
              ┌──────────┴──────────┐
              │ profile → tabId     │  (查标签映射)
              │ main  → tabId=42    │
              │ dsg   → tabId=43    │
              └──────────┬──────────┘
                         │
              forwardToChatGPT(text, tabId)
```

### 2.3 上下文清理时机

| 触发条件 | 操作 |
|----------|------|
| 手动 (CY 决定) | 刷新对应 profile 标签页 |
| 对话轮次 > 30 | 扩展自动刷新标签页，重建对话 |
| GPT 输出 `##CLEAR_CONTEXT##` | 扩展刷新标签页 |

---

## 3. Bridge Server 多实例改造

### 3.1 GptLoopEngine 实例化

```python
# bridge_server.py 启动时创建多实例

PROFILES = {
    "main":  {"api_url": "http://127.0.0.1:18642/v1/chat/completions",
              "api_key_env": "API_SERVER_KEY_MAIN",
              "chat_id": "gpt_loop_main"},
    "dsg":   {"api_url": "http://127.0.0.1:18645/v1/chat/completions",
              "api_key_env": "API_SERVER_KEY_DSG",
              "chat_id": "gpt_loop_dsg"},
    "ops":   {"api_url": "http://127.0.0.1:18643/v1/chat/completions",
              "api_key_env": "API_SERVER_KEY_OPS",
              "chat_id": "gpt_loop_ops"},
    "sales": {"api_url": "http://127.0.0.1:18647/v1/chat/completions",
              "api_key_env": "API_SERVER_KEY_SALES",
              "chat_id": "gpt_loop_sales"},
}

gpt_loops = {}
for profile, cfg in PROFILES.items():
    api_key = os.getenv(cfg["api_key_env"], "")
    store = PendingStore()
    responses = {}
    gpt_loops[profile] = GptLoopEngine(
        pending_queue=store,
        response_store=responses,
        api_key=api_key,
        chat_id=cfg["chat_id"],
    )
    # 设置 MAIN_API_URL 覆盖
    gpt_loops[profile].MAIN_API_URL = cfg["api_url"]
```

### 3.2 路由规则

| 消息来源 chat_id | 路由到 profile |
|------------------|----------------|
| `oc_f9079b...` (主群) | main |
| `oc_d3ea70...` (DSG 群) | dsg |
| `oc_31a5db...` (OPS 群) | ops |
| `oc_79c3b3...` (SALES 群) | sales |
| `gpt_loop` / `gpt_loop_main` | main (向后兼容) |

### 3.3 Endpoint 变更

| Endpoint | 旧 | 新 |
|----------|-----|-----|
| `/gpt-loop/start` | 只操作 main | `POST {profile, task}` 指定 profile |
| `/gpt-loop/status` | 只返回 main | `GET ?profile=main` 或全部 `?profile=all` |
| `/gpt-loop/stop` | 只停 main | `POST {profile}` 指定 |

### 3.4 State 文件隔离

```
~/.hermes/gpt_loop/
├── gpt_loop_state_main.json
├── gpt_loop_state_dsg.json
├── gpt_loop_state_ops.json
├── gpt_loop_state_sales.json
└── archive/
    ├── main/
    ├── dsg/
    ├── ops/
    └── sales/
```

### 3.5 Pending 队列 tag 路由

每个 profile 的 GptLoopEngine 有独立的 PendingStore。消息从 `/send` 进入时，根据 chat_id 路由到对应 profile 的 PendingStore：

```python
def _route_message(entry):
    chat_id = entry.get("chat_id", "")
    profile = ROUTE_MAP.get(chat_id, "main")
    gpt_loops[profile]._queue_pending(entry["text"])
```

---

## 4. Chrome 扩展改造

### 4.1 标签页管理 (background.js 新增)

```js
// 标签页映射: profile → tabId
var g_profileTabs = {
  main: null,
  dsg: null,
  ops: null,
  sales: null
};

// 路由表: chat_id → profile
var ROUTE_MAP = {
  'oc_f9079b6cada48b388b8b4af140fb6973': 'main',
  'oc_d3ea70740545bc1235822c395ce02bea': 'dsg',
  'oc_31a5db5efcfda89380177642f8e91619': 'ops',
  'oc_79c3b382ee58018dceb155666490253e': 'sales',
};

async function getOrCreateTab(profile) {
  // 检查已有标签是否仍有效
  var tabId = g_profileTabs[profile];
  if (tabId) {
    try {
      await chrome.tabs.get(tabId);
      return tabId;  // 标签仍存在
    } catch(e) {
      g_profileTabs[profile] = null;
    }
  }
  
  // 打开新标签页
  var tab = await chrome.tabs.create({
    url: 'https://chatgpt.com/',
    active: false  // 后台打开，不抢焦点
  });
  g_profileTabs[profile] = tab.id;
  
  // 等待加载完成后注入 content script
  await new Promise(r => setTimeout(r, 2000));
  await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: () => { window.__BRIDGE_PROFILE = arguments[0]; },
    args: [profile]
  });
  
  return tab.id;
}
```

### 4.2 pollBridge 改造

```js
async function pollBridge() {
  var resp = await fetch(BRIDGE_URL + '/pending');
  var msgs = (await resp.json()).messages || [];
  if (!msgs.length) return;

  var ackedIds = [];
  for (var msg of msgs) {
    var profile = ROUTE_MAP[msg.chat_id] || 'main';
    var tabId = await getOrCreateTab(profile);
    
    // 路由到对应标签页
    await forwardToChatGPT(msg.text, tabId);
    ackedIds.push(msg._id);
  }
  
  // ACK
  await fetch(BRIDGE_URL + '/pending/ack', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ids: ackedIds})
  });
}
```

### 4.3 上下文清理

```js
// 每个 profile 的对话轮次计数
var g_profileRounds = {main: 0, dsg: 0, ops: 0, sales: 0};

const MAX_ROUNDS = 30;

async function checkContextClear(profile) {
  g_profileRounds[profile] = (g_profileRounds[profile] || 0) + 1;
  if (g_profileRounds[profile] >= MAX_ROUNDS) {
    var tabId = g_profileTabs[profile];
    if (tabId) {
      await chrome.tabs.reload(tabId);
      g_profileRounds[profile] = 0;
    }
  }
}
```

---

## 5. run_bridge.sh 更新

```bash
# 加载所有 profile 的 API key
for p in main dsg ops sales; do
    ENV_FILE="$HOME/.hermes/profiles/$p/.env"
    [ -f "$ENV_FILE" ] && export $(grep "^API_SERVER_KEY=" "$ENV_FILE" | xargs | sed "s/API_SERVER_KEY/API_SERVER_KEY_${p^^}/")
done

# Bridge 端口改为 18640
python3 bridge_server.py --port 18640
```

---

## 6. 施工阶段

**灰度策略：DSG 先行，MAIN 不动。**

| 阶段 | 内容 | 影响范围 |
|------|------|----------|
| **Phase 1** | Bridge 端口迁移 18643→18640，释放 18643 给 OPS | Bridge 重启，MAIN 链路短暂中断 |
| **Phase 2** | bridge_server.py 多 GptLoopEngine 实例（先只加 DSG） | 仅新增 DSG loop，MAIN loop 不变 |
| **Phase 3** | background.js 多标签页管理 + DSG 路由 | 仅新增 DSG 标签页，MAIN 路由不变 |
| **Phase 4** | content.js 注入 profile 标记 | 所有标签页，向后兼容 |
| **Phase 5** | DSG 独立回归测试（不涉及 MAIN） | 仅 DSG，MAIN 零影响 |
| **Phase 6** | DSG 验收通过后，按序扩 OPS → SALES | 渐进扩展 |

---

## 7. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 多标签页内存/CPU 占用 | 后台标签页 Chrome 自动节流；不超过 4 个 profile |
| Bridge 单进程瓶颈 | Python HTTP server 可处理并发；如有压力改为 gunicorn |
| Profile 间消息串扰 | chat_id→profile 路由表硬编码；content script 注入 profile 标记双重校验 |
| 标签页被用户误关 | `getOrCreateTab` 自动重建 |
| 上下文过长导致 GPT 质量下降 | 30 轮自动清理；CY 可手动 `/clear` |

---

## 8. 待 CY 确认

1. Profile 范围：main + dsg + ops + sales 四个，还是先只做 dsg？
2. 上下文清理阈值：30 轮合适吗？
3. OPS 的 18643 端口冲突：先修还是灰度完成后再修？
4. Sales API key 是否需要更严格隔离（当前在 .env 中明文）？
