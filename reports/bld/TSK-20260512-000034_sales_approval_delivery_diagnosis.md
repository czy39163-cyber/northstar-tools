# TSK-20260512-000034 — SALES 客户查询审批送达链路 定位诊断报告

**任务类型**: 定位段（只读分析，不修改任何文件）
**分析日期**: 2026-05-12
**分析人**: BLD / 铁甲虾
**状态**: 定位完成

---

## 一、涉及文件清单

| 文件 | 行数 | 版本 | 说明 |
|------|------|------|------|
| `~/.hermes/scripts/pending_approval.py` | 554 | v2.2 | CLI 脚本：创建/管理 pending 记录、路由补全、占位文本检测 |
| `~/.hermes/profiles/sales/hooks/sales-approval-check/handler.py` | 316 | v2.2 | Hook：监听 CY 审批消息 → 三级兜底送达 |
| `~/.hermes/profiles/sales/SOUL.md` | 541 | v2.3 | SALES 人设/行为规范，含 CCPC360 查询流程、pending 创建指令 |
| `~/.hermes/profiles/sales/pending_approvals.json` | 245 | — | 待审批数据（13 条历史记录） |
| `~/.hermes/profiles/sales/sessions/sessions.json` | 212 | — | 会话路由数据（6 个活跃 session） |

---

## 二、当前数据流全景（步骤 1→8）

```
步骤1: 查询人在飞书 DM/群聊 @ SALES，请求查询某项目联系人
   ↓
步骤2: SALES 模型调用 terminal() 执行 ccpc360_query.py search/contacts
        → 从 CCPC360 数据库获取完整联系人数据（含姓名+手机+职位）
        → 此时完整数据在模型上下文（terminal 输出）中
   ↓
步骤3: SALES 根据 SOUL.md 辖区映射表判断权限
        → 查询人 = 辖区负责人 → 直接输出（无需审批）
        → 查询人 ≠ 辖区负责人 → 进入审批流程
   ↓
步骤4: SALES 调用 pending_approval.py add 创建待审批记录
        → 模型将 contact_details 作为 CLI 第5位置参数传入
        → --auto-routing <chat_id> 从 sessions.json 补全路由字段
        → _is_placeholder() 检测 contact_details → 标记 contact_details_valid
   ↓
步骤5: pending 记录写入 pending_approvals.json
        → 若 contact_details 为占位文本 → contact_details_valid=false
        → 若 contact_details 为真实数据 → contact_details_valid=true
   ↓
步骤6: SALES 向 CY 发送脱敏审批申请（format_privacy_approval_request）
   ↓
步骤7: CY 回复审批关键词（审批通过/拒绝）
        → Hook（handler.py）在 agent:start 时自动触发
        → 匹配 pending 记录 → 更新 status=approved/rejected
   ↓
步骤8: handler._send_approval_result() 执行三级兜底送达
        → 校验 contact_details 有效性（v2.2 BLOCK 安全网）
        → 有效 → L1私信/L2回群/L3兜底
        → 占位文本 → BLOCKED，发 blocked_msg 到 SALES_HOME_CHANNEL
```

---

## 三、根因分析（分层）

### 层1: 数据源层 — CCPC360 查询

**状态**: ✅ 正常。`ccpc360_query.py contacts` 能返回完整联系人数据（含姓名+手机+职位），已在多条记录中验证。

**证据**:
- 记录 `20260512103619`（广东三津）: contact_details 包含完整的 22 位联系人姓名+手机+职位，格式正确（`\n` 分隔+`|`分隔符），通过 _is_placeholder 检测。
- 记录 `20260512091420`（佳鸿潮玩）: contact_details 包含完整联系人数据，送达成功 delivery_status=delivered_to_requester_dm。

**结论**: 数据源不是瓶颈。CCPC360 能产出合格数据。

---

### 层2: CLI 传输层 — 模型将数据传入 pending_approval.py ⚠️ **核心断点**

**状态**: ❌ 不稳定。这是送达链路的核心瓶颈。

**证据 — 同一项目（广东三津）的三次对比**:

| 记录 ID | contact_details | 是否真实数据 | 结果 |
|---------|----------------|-------------|------|
| `20260512103619` | `【业主】广东三津食品有限公司\n彭苏城 \| 15323517606 \| 项目知情人\n...（22人完整）` | ✅ 是 | 审批通过，contact_details 合格 |
| `20260512114111` | `已获取22位联系人（业主8人、设计8人、施工5人），待审批后输出` | ❌ 占位 | 审批通过，但送达的是占位文本 |
| `20260512133106` | `已获取22位联系人，待CY审批后按权限输出完整信息` | ❌ 占位 | pending，contact_details_valid=false |
| `20260512133127` | `已获取22位联系人：业主广东三津食品有限公司共彭苏城、方增满...` | ❌ 占位 | pending，contact_details_valid=false（人名列表但无手机号+结构） |

**根因定位**:

模型行为不一致，**不是 SOUL 指令问题，不是模型能力问题，而是 CLI 参数传输的固有脆弱性**。

具体机制：

1. **上下文长度压力** — 当模型刚执行完 CCPC360 查询，22 位联系人的完整输出在上下文中，模型能将其复制到 CLI 命令。但随着对话轮次增加，上下文被其他内容稀释，模型倾向于"总结"而非"原样复制"。

2. **CLI 参数的心理模型偏差** — 尽管 SOUL.md 第 196-208 行明确给出了 ✅/❌ 示例，模型在多轮对话后仍会退化为"摘要模式"。模型将 `contact_details` 理解为"给人看的描述"而非"给 handler 的机器可读数据"。

3. **Shell 转义风险** — 22 位联系人的完整数据包含换行符 `\n`、管道符 `|`、中文括号等特殊字符。模型在构造 CLI 命令时，换行符需要写为 `\\n` 或实际换行，管道符可能被 shell 误解。这增加了模型正确构造命令的认知负担。

4. **v2.2 BLOCK 安全网有效但被动** — `_is_placeholder()` 能检测占位文本并标记 `contact_details_valid=false`，handler 能阻止占位文本送达。但这是**防御性措施**，不能**修复数据**。BLOCK 后查询人仍然收不到联系人信息。

**关键发现**: 记录 `20260512103619` 证明模型**有能力**传入完整数据。记录 `20260512114111`（仅 25 分钟后）证明模型**不稳定**。这是一个**概率性失败**，不是绝对失败。

---

### 层3: Handler 读取层

**状态**: ✅ 正常。Handler 正确实现了三级兜底送达 + BLOCK 安全网。

**验证点**:
- `_is_placeholder_text()` 逻辑与 `pending_approval.py._is_placeholder()` 一致（关键词检测+长度检测+结构检测）
- 三级兜底 L1/L2/L3 正确执行
- v2.2 BLOCK 路径正确阻止占位文本送达，并发送 blocked_msg 到 SALES_HOME_CHANNEL
- `contact_details_valid` 标记在 pending 记录中正确写入和读取

**Handler 的局限**: Handler 只能读取 pending 记录中已有的 contact_details。如果数据在步骤4（CLI 传输）就已经是占位文本，handler 无法恢复原始数据。这是**数据流上游问题**，不是 handler 问题。

---

## 四、逐项回答问题

### a. contact_details 在哪个环节产生？模型从哪里获取联系人数据？

**产生环节**: 步骤2 — SALES 模型调用 `ccpc360_query.py contacts {project_id}`，terminal() 工具返回的 stdout。

**数据来源**: CCPC360（找项目网）数据库，通过 `ccpc360_query.py` 脚本查询。

**关键**: 完整联系人数据**只存在于模型上下文**（terminal 输出）中。没有独立的文件缓存、没有数据库持久化、没有 API 响应缓存。一旦模型会话结束或上下文被驱逐，完整数据就永久丢失。

---

### b. 模型为什么反复传入占位文本而非真实数据？

**不是 SOUL 指令问题**。SOUL.md 第 180-219 行已经用极强语言（🔴🔴🔴、✅/❌ 对照、数据流全景图）反复强调必须传完整原文。但模型仍然不稳定。

**不是模型能力问题**。记录 `20260512103619` 证明模型能正确传出 22 位联系人的完整数据。

**是 CLI 参数传输的固有脆弱性**（三个子原因）：

| 子原因 | 机制 | 影响 |
|--------|------|------|
| 上下文稀释 | 多轮对话后 CCPC360 输出被后续消息挤出有效上下文窗口，模型无法"回忆"完整原文 | 模型退化为摘要 |
| 心理模型偏差 | 模型将 CLI 参数理解为"人读描述"而非"机器读数据"，尽管 SOUL.md 反复纠正 | 模型写"待审批后输出" |
| Shell 复杂度 | 22 人完整数据含特殊字符（管道符、换行符、中文），模型构造 CLI 命令时需要额外转义 | 增加错误概率 |

**本质**: 这是一个**人机接口设计问题**。让 LLM 通过 CLI 参数传递结构化长数据，就像让人类把一段 500 字的地址口述给快递员——有时能说对，有时会漏掉门牌号。

---

### c. artifact/cache 方案可行性和可靠性

**方案描述**: 创建 pending 时将联系人数据写入独立文件，handler 从文件读取。

**数据来源**: 模型从 CCPC360 查询结果（terminal 输出）获取 → 写入文件。

**可靠性评估**: ⚠️ 中等。这仍然依赖模型正确执行文件写入操作。优势是：
- 文件写入比 CLI 参数传递更不受 shell 转义影响
- 文件可以更大（不受 ARG_MAX 限制）
- 但模型仍需从上下文中提取完整数据并写入

**更优方案**: **脚本级自动缓存**。修改 `ccpc360_query.py` 在 `contacts` 子命令执行时自动将完整输出写入缓存文件。这样：
- 缓存文件由脚本直接写入（不受模型行为影响）
- 模型只需引用缓存文件路径/项目 ID
- handler 直接读取缓存文件

---

### d. 其他捕获路径评估

| 路径 | 可行性 | 评估 |
|------|--------|------|
| CCPC360 API 缓存 | ✅ 高 | 修改 `ccpc360_query.py contacts` 执行时自动写缓存到约定路径。模型零参与，100% 可靠 |
| 模型内部状态 | ❌ 不可行 | 模型内部状态不可被外部进程访问 |
| 飞书消息历史 | ❌ 不可行 | 模型发给 CY 的审批申请是脱敏预览（`contact_preview`），不含完整手机号 |
| sessions.json | ❌ 不适用 | sessions.json 存储路由信息，不存储联系人数据 |
| 模型 Write 工具写入文件 | ⚠️ 中等 | 依赖模型行为，与 CLI 传参有类似脆弱性 |

**唯一可靠的捕获路径是脚本级自动缓存**: 让 `ccpc360_query.py` 在查询联系人时自动将结果写入 `~/.hermes/profiles/sales/cache/contacts_{project_id}.json`，与模型行为完全解耦。

---

### e. pending_approval.py 设计脆弱点

| 脆弱点 | 位置 | 说明 |
|--------|------|------|
| **contact_details 为 CLI 位置参数** | `add_pending()` 第5参数, CLI `add` 第5位置参数 | 依赖模型在命令字符串中嵌入完整长文本。受 shell 转义、ARG_MAX、模型摘要倾向三重影响。**这是当前设计的最大脆弱点** |
| **--auto-routing 依赖 sessions.json 存在** | `resolve_routing_from_session()` L101 | 如果 SALES session 尚未创建（新对话），路由解析失败，但没有阻塞机制——pending 仍会创建但 routing_fields=false |
| **contact_details 无数据完整性校验** | `_is_placeholder()` L42-78 | 只能检测"明显占位"（关键词、长度、结构），不能检测"数据不完整"（如只传了 8 人而非 22 人） |
| **delivery_target 写入时机** | CLI `add` L469 | delivery_target 在 `add_pending()` 返回后才通过二次 `_load()→_save()` 写入，存在微小的竞态窗口（同一秒内 hook 读取） |
| **add_pending 和 routing 元数据分两次写入** | CLI `add` L443-471 | `add_pending()` 创建记录后，再 `_load()→修改→_save()` 写入 routing 元数据。如果在两次写入间 hook 触发，可能读到不完整的记录 |

---

## 五、artifact/cache 设计建议

### 方案 A（推荐）: CCPC360 脚本级自动缓存

修改 `ccpc360_query.py contacts` 子命令，查询成功后自动将完整输出写入约定路径：

```
缓存路径: ~/.hermes/profiles/sales/cache/contacts_{project_id}.json
写入时机: ccpc360_query.py contacts 子命令执行成功时
读取时机: handler._send_approval_result() 从缓存文件读取
```

**优点**:
- 模型零参与，100% 消除模型行为不稳定性
- 脚本直接写入，数据完整性由脚本保证
- handler 直接读取文件，不依赖 pending 中的 contact_details 字段
- 向后兼容：如果缓存文件不存在，回退到 pending 中的 contact_details

**缺点**:
- 需要修改 `ccpc360_query.py`（新增缓存写入逻辑）
- 需要处理缓存清理（过期缓存）

### 方案 B（备选）: pending_approval.py 接受文件引用

```
python3 pending_approval.py add "项目" "查询人" "辖区" "预览" \
  --contact-artifact /path/to/contacts.json \
  --auto-routing <chat_id>
```

**优点**: 不修改 CCPC360 脚本。
**缺点**: 模型仍需先写文件再传路径——两步操作，仍有模型行为风险。

### 建议: 方案 A 为主，方案 B 为兼容通道。优先实施 A。

---

## 六、pending 字段变更建议

新增字段：

```json
{
  "contact_artifact_path": "cache/contacts_1855768437552332802.json",
  "contact_artifact_source": "ccpc360_cache"
}
```

原有字段保留（向后兼容）：

```json
{
  "contact_details": "...",           // 保留：作为 artifact 不存在时的 fallback
  "contact_details_valid": true,      // 保留：BLOCK 安全网
  "contact_details_placeholder_reason": null
}
```

读取优先级：

```
1. contact_artifact_path 指向的文件存在且可读 → 使用文件内容
2. contact_details_valid=true → 使用 contact_details
3. 其他 → BLOCKED
```

---

## 七、handler 读取 artifact 的逻辑建议

在 `_send_approval_result()` 中增加 artifact 优先读取逻辑（伪代码）：

```python
def _read_contact_details(matched):
    # 优先级1: artifact 文件
    artifact_path = matched.get("contact_artifact_path")
    if artifact_path:
        full_path = os.path.join(CACHE_DIR, artifact_path)
        if os.path.exists(full_path):
            with open(full_path) as f:
                data = json.load(f)
            return data["contacts_text"], True, None
    
    # 优先级2: pending 中的 contact_details（现有逻辑）
    contact_details = matched.get("contact_details", "")
    is_ph, reason = _is_placeholder_text(contact_details)
    if not is_ph:
        return contact_details, True, None
    
    # 优先级3: 都是占位 → BLOCKED
    return contact_details, False, reason
```

**BLOCK 条件保留**: v2.2 的 `_is_placeholder_text()` 保留为最后一道防线。即使 artifact 缓存机制上线，也需要防止缓存文件损坏/为空的情况。

---

## 八、最小 patch 范围

如果进入补丁段施工，需要修改：

| 文件 | 函数/位置 | 改动说明 |
|------|----------|----------|
| `ccpc360_query.py` | `cmd_contacts()` | 新增：查询成功后自动写入缓存文件到 `~/.hermes/profiles/sales/cache/contacts_{project_id}.json` |
| `pending_approval.py` | `add_pending()` | 新增 `contact_artifact_path` 参数，新增 `--contact-artifact` CLI 参数 |
| `pending_approval.py` | CLI `add` 子命令 | 读取 artifact 路径并写入 pending 记录 |
| `handler.py` | `_send_approval_result()` | 新增 `_read_contact_details()` 函数，artifact 优先读取 |
| `SOUL.md` | 第十二节 | 更新 pending_approval.py add 示例，增加 `--contact-artifact` 参数说明 |

**不改的文件**: sessions.json、pending_approvals.json 数据结构（只增加可选字段）

---

## 九、风险点

| 风险 | 等级 | 缓解 |
|------|------|------|
| CCPC360 脚本修改引入回归 bug | 中 | 仅修改 contacts 子命令，不影响 search；先做 backup |
| 缓存文件堆积（磁盘占用） | 低 | 设置 TTL（7 天），定时清理 |
| 缓存文件包含真实手机号（安全） | 中 | 缓存目录权限 700，不纳入 git |
| Handler 读取缓存失败（文件不存在） | 低 | 三级回退：artifact → contact_details → BLOCKED |
| 旧 pending 记录无 artifact_path 字段 | 低 | 向后兼容，handler 按优先级读取 |

---

## 十、验收命令

```bash
# 1. 验证 CCPC360 查询自动写缓存
python3 ~/.hermes/scripts/ccpc360_query.py contacts 1855768437552332802
ls -la ~/.hermes/profiles/sales/cache/contacts_1855768437552332802.json

# 2. 验证 pending_approval.py 接受 --contact-artifact
python3 ~/.hermes/scripts/pending_approval.py add \
  "测试项目" "测试用户" "测试辖区" "预览" "fallback文本" \
  --contact-artifact cache/contacts_1855768437552332802.json \
  --auto-routing oc_c09415a1314d82a2aa751d0ee2c0008d

# 3. 验证 handler 能从 artifact 读取
grep "delivery_status" ~/.hermes/profiles/sales/pending_approvals.json

# 4. 验证 BLOCK 兜底仍有效（传占位文本不带 artifact）
python3 ~/.hermes/scripts/pending_approval.py add \
  "测试项目2" "测试用户2" "测试辖区2" "预览2" "待审批后输出"
# 应输出: WARNING: contact_details_valid=False
```

---

## 十一、结论

### 是否建议进入补丁段: **YES**

**理由**:

1. **根因明确**: CLI 参数传输是核心瓶颈，不是模型问题或 SOUL 指令问题。v2.2 的 BLOCK 安全网有效但只能防御不能修复。

2. **修复方案清晰**: CCPC360 脚本级自动缓存是最高可靠性的方案——让数据流绕过模型，从脚本直接到文件再到 handler。模型只需传项目 ID / artifact 路径引用。

3. **当前状态不可接受**: pending_approvals.json 中 13 条记录有 7 条（54%）的 contact_details 为占位文本。每次 BLOCK 意味着查询人发起查询 → CY 审批通过 → 查询人仍然收不到联系人信息。这是面向用户的可见故障。

4. **patch 范围可控**: 约 3 个文件、5 个函数/位置，预计 <150 行改动。属于小补丁范围。

5. **向后兼容**: 新增 artifact 读取路径，保留现有 BLOCK 安全网和 contact_details 字段。旧 pending 记录不受影响。

**建议施工顺序**: 先做 `ccpc360_query.py` 缓存写入 → 再做 `handler.py` artifact 读取 → 最后更新 `pending_approval.py` 和 `SOUL.md`。

---

*报告结束。等待 MAIN 审查并决定是否进入补丁段。*
