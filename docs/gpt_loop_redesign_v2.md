# GPT-Loop 架构重设 v2 — 施工规范

**日期**: 2026-05-17  
**MAIN 指令**: CY 睡觉后自主完成  
**架构决策**: 保留 Bridge + Chrome 扩展可见交互，逻辑层从 Bridge 剥离到 MAIN 侧  

---

## 一、新架构总览

```
                    ChatGPT Web UI
                          ↕ (Chrome Extension 不变)
              ┌──────────────────────────┐
              │   Bridge Server (瘦身)    │
              │                          │
              │  仅保留:                  │
              │  · PendingStore (队列)    │
              │  · RESPONSES (响应存储)   │
              │  · /send → 入队          │
              │  · /pending → 出队       │
              │  · /pending/ack → 销账   │
              │  · /response → 存储响应   │
              │  · /health → 健康检查     │
              │  · /log → 最近日志        │
              │                          │
              │  ❌ 移除:                 │
              │  · GptLoopEngine          │
              │  · 所有 /gpt-loop/*       │
              │  · /main-feedback         │
              │  · is_loop_control 逻辑   │
              └──────────┬───────────────┘
                         ↕ HTTP
              ┌──────────┴───────────────┐
              │  gpt_loop_controller.py  │
              │  (全新, 独立进程)         │
              │                          │
              │  轮询 Bridge /response   │
              │  解析 @MAIN: 指令         │
              │  调 MAIN API 执行         │
              │  结果发回 Bridge /send    │
              │  管理状态文件             │
              │  安全规则 R1/R2/R3        │
              │  写入 task_ledger         │
              └──────────────────────────┘
```

## 二、Chrome 扩展 — 不变

扩展的 background.js 和 content.js 完全不动。它继续：
1. 每隔 60s 轮询 Bridge `/pending`
2. 将消息注入 ChatGPT 输入框
3. 捕获 ChatGPT 回复
4. 发 POST `/response` 到 Bridge

**扩展已有的 gpt_loop 路径判定逻辑继续正常工作**：
- `@MAIN:` / `##TASK_DONE##` / `##PROJECT_CLOSED##` 标记的消息 → 跳过飞书，只发 Bridge
- 普通消息 → 同时发飞书 webhook 和 Bridge

---

## 三、Bridge Server — 改动清单

### 3.1 删除的代码

| 文件 | 删除内容 | 替代方案 |
|------|----------|----------|
| `from gpt_loop import GptLoopEngine, LoopState` | 整行删除 | 不再需要 |
| `gpt_loop: GptLoopEngine = None` | 全局变量 | 无 |
| `BridgeHTTP._route_loop_command()` | 整个方法 | 控制器直接 POST /send |
| `BridgeHTTP._handle_loop_response()` | 整个方法 | 控制器直接处理 |
| `BridgeHTTP._handle_loop_start()` | 整个方法 | 无 |
| `BridgeHTTP._handle_loop_stop()` | 整个方法 | 无 |
| `BridgeHTTP._handle_loop_pause()` | 整个方法 | 无 |
| `BridgeHTTP._handle_loop_resume()` | 整个方法 | 无 |
| `BridgeHTTP._handle_main_feedback()` | 整个方法 | 无 |
| `do_POST` 中 `/gpt-loop/*` 和 `/main-feedback` 路由 | 删除 | 返回 404 |
| `do_GET` 中 `/gpt-loop/status` 路由 | 删除 | 返回 404 |
| `main()` 中 gpt_loop 初始化和 state restore | 删除 | 无 |

### 3.2 修改的代码

**_handle_response** 中，当前有 `is_loop_control` 拦截逻辑。改为更简单的规则：

```python
# 代替 is_loop_control 逻辑：
# 任何包含 @MAIN: / ##TASK_DONE## / ##PROJECT_CLOSED## 的消息
# → 存入 RESPONSES["gpt_loop"]（不经过 GptLoopEngine）
# → 控制器将来轮询这个队列
has_loop_marker = "@MAIN:" in text or "##TASK_DONE##" in text or "##PROJECT_CLOSED##" in text
if has_loop_marker:
    store_key = "gpt_loop"
else:
    store_key = chat_id
if store_key not in RESPONSES:
    RESPONSES[store_key] = []
RESPONSES[store_key].append({'text': text, 'ts': time.time()})
```

**do_POST 中的 `/send` 处理**：删除 `text.startswith('gpt-loop ')` 的特殊路由，全部走普通入队逻辑。

### 3.3 Bridge Server 最终 endpoint 清单

| Endpoint | 方法 | 功能 |
|----------|------|------|
| `/health` | GET | 健康检查 |
| `/pending` | GET | 取出待处理消息 |
| `/pending/ack` | POST | 确认处理完毕 |
| `/response` | POST | 接收 ChatGPT 响应 |
| `/send` | POST | 接收外部消息入队 |
| `/log` | GET | 查看最近日志 |

### 3.4 run_bridge.sh — 不变

仍从 `~/.hermes/profiles/main/.env` 加载 API_SERVER_KEY。保留但不使用（将来控制器会用）。删除 No GptLoopEngine warning message。

---

## 四、gpt_loop.py — 重构为工具库

原 `GptLoopEngine` 类全部删除，只保留可复用的数据结构和工具函数：

### 4.1 保留/重构的内容

```python
# 数据类（保留，供控制器 import）
@dataclass
class RoundRecord:
    round_num: int
    gpt_instruction: str
    main_instruction: str
    main_result: str
    status: str  # completed | failed | skipped | refused
    timestamp: str

# 安全函数（保留，供控制器 import）
def check_safety(instruction: str, task: str = "") -> dict:
    """Apply R1/R2/R3 safety rules. Returns {"level": "low"|"medium"|"high", ...}"""

def strip_feishu_wrapper(text: str) -> str:
    """Remove Feishu/Bridge formatting wrappers"""

# 常量（保留）
MAX_ROUNDS = 50
MAIN_API_URL = "http://127.0.0.1:18642/v1/chat/completions"
MAIN_API_TIMEOUT = 300
```

### 4.2 删除的内容

- `LoopState` 枚举类（控制器用简单状态字符串）
- `LoopStateCard` 数据类（控制器用更简单的状态结构）
- `GptLoopEngine` 类（全部方法）
- `STATE_DIR`, `STATE_FILE`, `ARCHIVE_DIR` 常量（控制器自己管理）
- 所有 Feishu 正则包装（`RE_FEISHU_PREFIX`, `RE_FEISHU_SUFFIX`）
- 所有 `_RE_NEGATION` 等内部辅助正则

---

## 五、gpt_loop_controller.py — 全新控制器

### 5.1 位置

`/home/cy/northstar-tools/gpt_loop_controller.py`

### 5.2 职责

1. **状态管理**：JSON 状态文件 `~/.hermes/gpt_loop/controller_state.json`
2. **轮询 Bridge**：GET `http://127.0.0.1:18643/response?chat_id=gpt_loop`
3. **解析 GPT 响应**：提取 `@MAIN:` 指令、检测 `##TASK_DONE##`
4. **安全检测**：调用 `gpt_loop.check_safety()` 的 R1/R2/R3 规则
5. **执行指令**：POST 到 MAIN API `http://127.0.0.1:18642/v1/chat/completions`
6. **回写结果**：POST `/send` 到 Bridge，sender="gpt_loop"，chat_id="gpt_loop"
7. **持久化**：每轮写入状态文件 + 存档
8. **终止检测**：`##TASK_DONE##` → 完成；连续 3 次格式错误 → 暂停

### 5.3 命令行接口

```bash
# 启动新任务
python3 gpt_loop_controller.py start "北极星1A 检查所有客户状态"

# 查看状态
python3 gpt_loop_controller.py status

# 暂停
python3 gpt_loop_controller.py pause

# 恢复
python3 gpt_loop_controller.py resume

# 停止
python3 gpt_loop_controller.py stop
```

### 5.4 状态文件结构

```json
{
  "state": "idle|running|paused|done",
  "task_id": "gpt_loop_20260517_030000",
  "task": "任务描述",
  "round": 5,
  "max_rounds": 50,
  "completed_steps": ["Round 1: xxx", "Round 2: yyy"],
  "recent_rounds": [...],
  "compacted_rounds": 0,
  "consecutive_errors": 0,
  "chat_id": "gpt_loop",
  "updated_at": "2026-05-17T03:00:00Z"
}
```

### 5.5 核心循环逻辑

```
while state == "running":
    1. Poll GET /response?chat_id=gpt_loop
    2. If no response: sleep 3s, continue
    3. Parse response:
       - strip_feishu_wrapper()
       - Check ##TASK_DONE## → stop
       - Check @MAIN: → extract instruction
       - If no instruction: increment error count
         error >= 3 → pause, report
    4. Safety check: check_safety(instruction)
       - high → pause, report reason
       - medium → forward with warning flag
    5. Forward instruction to MAIN API (POST /v1/chat/completions)
    6. Parse MAIN response
    7. Record round (RoundRecord)
    8. Send result back: POST /send with sender="gpt_loop"
    9. Update state file
    10. Sleep 1s → back to 1
```

### 5.6 与 MAIN API 的认证

从 `~/.hermes/profiles/main/.env` 的 `API_SERVER_KEY` 加载。
初始化时读取一次。

---

## 六、施工阶段与验收

### Phase 1: Bridge 瘦身
- 修改: `bridge_server.py`
- CC 任务: 删除 GptLoopEngine 集成 + 清理 endpoint + 简化 _handle_response
- 验收: Bridge 重启后 `/health` 正常、/send→/pending 正常、/response 存储正常

### Phase 2: 控制器创建
- 创建: `gpt_loop_controller.py`
- CC 任务: 全新脚本，完成 5.1-5.6 全部功能
- 验收: 能 start/stop/status，能用 curl mock 跑通 1 轮

### Phase 3: 5 轮集成测试
- 不涉及代码修改
- 启动真实 Bridge → 启控制器 → 跑 5 轮轮询
- 验证: 全部 5 轮 completed，安全检测正常，状态文件完整

---

## 七、安全规则

### 禁止事项（硬 R1）
- 不读 .env、不输出 API key/token/secret
- 不修改 config.yaml
- 不重启 gateway
- 不广播飞书全量

### 防护规则
- 连续 3 次格式错误 → 自动暂停
- 敏感词检测到主动读取意图 → 暂停 + 报警
- 指令与任务无关键词重叠 → 告警但不阻塞
- 模糊指令（"maybe/try/试试"）→ 告警
