# BLD 多执行引擎调度落地方案 v1.0

> 定位：BLD（铁甲虾）建设层多引擎协同方案  
> 日期：2026-05-07  
> 状态：初稿，待确认  
> 约束：只写文档，不改代码，不建自动调度脚本

---

## 1. 当前结论

BLD 建设层维护三个可用的编码执行引擎：Claude Code（CC）、DeepSeek-TUI、Codex。

当前无自动调度层。引擎选择由 MAIN 手动判断 + 派单指令指定。BLD 本身无独立 profile，不接飞书，纯执行节点。

三引擎已安装就绪，各有明确适用场景和已知限制。现阶段不建自动路由，通过规则化的人工选择保证可控性。

---

## 2. 三引擎现状

| 引擎 | 安装路径 | 版本 | 后端模型 | 运行环境 | 当前状态 |
|------|----------|------|----------|----------|----------|
| Claude Code (CC) | `/home/cy/bin/claude-code-safe` → `/home/cy/.local/bin/claude` | latest | DeepSeek V4 Pro（通过 `ANTHROPIC_BASE_URL` 代理） | WSL, tmux 交互 / print mode | ✅ 生产可用 |
| DeepSeek-TUI | `/home/cy/bin/deepseek` + `/home/cy/bin/deepseek-tui` | v0.8.14 | DeepSeek V4 Pro / Flash | WSL, exec mode / TUI mode | ✅ 已安装，已验证 |
| Codex | Windows npm (`npx @openai/codex`) | latest | GPT-5.5 | Windows 侧（仅 `/mnt/c/...` 路径） | ✅ 已安装，路径受限 |

### 已知限制

- **CC**：大文件多段任务第 3 段起上下文膨胀卡死；print mode 600s 硬限制
- **DeepSeek-TUI**：与 CC 共享同一 DeepSeek API key，实际调同一模型；功能集较 CC 简单
- **Codex**：不能从 WSL 原生路径运行；token 消耗高（简单任务 ~22K tokens）；需要 git repo

---

## 3. CC / DeepSeek-TUI / Codex 定位

### Claude Code (CC) — 主力引擎

**定位**：复杂分析、多步工具调用、架构级任务的默认首选。

- tmux 交互模式：需实时审查 diff 的多段任务
- print mode：单次完整修改（< 500 行改动）
- pro 用途：架构判断、任务拆解、diff 审查、验收口径
- flash 用途：< 30 行精确补丁

### DeepSeek-TUI — 成本敏感 / 稳定性备选

**定位**：CC 不可用或成本敏感时的备选引擎。

- exec mode：非交互单次执行
- 适用：CC auth 失败、CC 超时、需要直连 DeepSeek API（无代理）
- 限制：功能集比 CC 简单，无 tmux 监控机制

### Codex — 独立视角 / GPT 能力补充

**定位**：需要 OpenAI 模型视角或批量 issue 处理时的可选引擎。

- exec mode：单次执行
- 适用：需要 GPT-5.5 的代码理解、PR review、多 worktree 并行修复
- 限制：WSL 路径不可用、token 消耗高、需 git repo

---

## 4. 引擎选择规则

### 默认优先级

```
1. CC（首选，走 tmux 或 print mode）
2. DeepSeek-TUI（CC 不可用时的 fallback）
3. Codex（需要 GPT 视角时的 optional）
```

### 场景路由

| 场景 | 首选 | 备选 | 说明 |
|------|------|------|------|
| 复杂架构改动 | CC tmux | DeepSeek-TUI | CC 多步工具调用能力最强 |
| 小补丁（<30 行） | CC flash | DeepSeek-TUI | 精简 prompt，快速完成 |
| 大文件多段重构 | CC tmux（每段重启） | — | 唯一能可靠处理的选择 |
| CC auth/超时 | DeepSeek-TUI | Codex | 直连 DeepSeek API |
| PR review / 批量修复 | Codex | CC | GPT-5.5 理解力 |
| 成本敏感任务 | DeepSeek-TUI | CC flash | DeepSeek API 单价最低 |
| 需要 git worktree | Codex | CC | Codex 原生支持 worktree |

---

## 5. 切换条件

### 重要前提：CC 与 DeepSeek-TUI 共用 DeepSeek 后端

CC 通过 `ANTHROPIC_BASE_URL` 代理实际调用 DeepSeek API，与 DeepSeek-TUI 共享同一后端和 API key。因此切换时必须区分问题层级：

- **CC 工具层面问题**（CLI 异常、tmux 会话崩溃、print mode 超时、项目上下文加载失败）→ 切 DeepSeek-TUI 有效
- **DeepSeek 后端层面问题**（provider 429 限流、API key 失效、后端不可用）→ 切 DeepSeek-TUI 不一定有效，应优先等待、降频、精简 prompt，必要时转 Codex

### 从 CC 切走

- CC 工具层面异常（CLI/auth/session 崩溃）→ 切 DeepSeek-TUI
- CC 单段超过 5 分钟无 diff 输出 → 中断，精简 prompt 重试 1 次；仍卡 → 切 DeepSeek-TUI
- CC print mode 超时（600s）→ 切 CC tmux 或 DeepSeek-TUI exec
- DeepSeek 后端 429/不可用 → **不切 DeepSeek-TUI**（无效）；等待 60s + 降频 + 精简 prompt；仍不可用 → 转 Codex（如路径条件满足）

### 从 DeepSeek-TUI 切走

- DeepSeek 后端 429/不可用 → 等待 60s + 精简 prompt；仍不可用 → 转 Codex
- 执行结果质量不达标 → 切 CC pro 做审查 + 修复

### 从 Codex 切走

- token 消耗异常高 → 切 CC 或 DeepSeek-TUI
- 路径不匹配 → 不可用 Codex，必须 CC 或 DeepSeek-TUI

### 回切 CC

- CC 恢复可用时，后续任务默认回 CC

---

## 6. 路径与密钥安全边界

### 路径规则

**路径安全纪律**：

所有执行引擎均受项目目录、白名单路径和任务边界限制，不得跨目录、跨盘、跨项目任意扫描或修改文件。

| 引擎 | 路径规则 | 说明 |
|------|---------|------|
| CC | 项目目录内，WSL 原生路径优先（`/home/cy/...`） | 受项目目录和白名单约束 |
| DeepSeek-TUI | 项目目录内，WSL 原生路径优先（`/home/cy/...`） | 受项目目录和白名单约束 |
| Codex | 按实际运行环境区分：Windows 原生执行时使用 `C:\`、`F:\` 等 Windows 路径；WSL 环境访问 Windows 文件时使用 `/mnt/c/`、`/mnt/f/` 等挂载路径 | 路径未确认时不得执行修改 |

**WSL 项目给 Codex 的处理方式**：建立 symlink 或同步到 Windows 路径。路径未确认时不得执行修改。

### 密钥管理

| 引擎 | Key 存储位置 | Key 类型 | 隔离状态 |
|------|-------------|----------|---------|
| CC | `~/.claude_code_env`（`ANTHROPIC_AUTH_TOKEN`） | DeepSeek API key | 与 DeepSeek-TUI 共享同一 key |
| DeepSeek-TUI | `~/.deepseek/config.toml` | DeepSeek API key | 与 CC 共享同一 key |
| Codex | OpenAI 环境变量 | OpenAI API key | 独立 |

**安全纪律**：

- 各引擎 key 不明文暴露在聊天、日志、截图、共享文档中
- CC 与 DeepSeek-TUI 共享同一 DeepSeek key，计费合并到同一 DeepSeek 账户
- Codex 使用独立 OpenAI key，计费合并到 OpenAI 账户
- Key 变更需更新对应存储文件，不通过代码中硬编码

---

## 7. Token / 成本控制规则

### 消耗特征

| 引擎 | 单任务典型消耗 | 单价参考 | 适用成本场景 |
|------|--------------|----------|-------------|
| CC (DeepSeek V4 Pro) | 中等 | DeepSeek 单价 | 性价比最优 |
| DeepSeek-TUI (Pro) | 中等 | DeepSeek 单价 | 与 CC 相同 |
| DeepSeek-TUI (Flash) | 低 | DeepSeek Flash 单价 | 最省钱 |
| Codex (GPT-5.5) | 高（~22K tokens/简单任务） | OpenAI 单价 | 最贵 |

### 成本控制纪律

1. **默认走 DeepSeek 系**（CC / DeepSeek-TUI），不主动选 Codex
2. **小任务走 flash**：< 30 行补丁优先 flash 模型
3. **Codex 仅在明确需要 GPT 能力时启用**，不做默认选择
4. **单任务 token 预估**：MAIN 派单前粗估，> 100K tokens 的任务必须先报 CY
5. **月度成本跟踪**：通过 DeepSeek / OpenAI 控制台查看用量，异常时 MAIN 告警

---

## 8. MAIN 手动选择 + BLD 分段执行流程

### 流程图

```
CY 提出建设任务
       │
       ▼
  MAIN 分诊 → 定为建设型任务（V2+）
       │
       ▼
  MAIN 判断引擎 → 按§4规则选择（CC / DeepSeek-TUI / Codex）
       │
       ▼
  MAIN 拆解任务 → 大任务拆为多段（定位段→补丁段→验证段）
       │
       ▼
  MAIN 派单 → 通过 tmux / exec 启动对应引擎
       │
       ▼
  MAIN 监控 → 按 skill 规则监控进度
       │
       ├─ 正常完成 → MAIN 独立验证 → 验收
       │
       ├─ 卡住/失败 → 按§5切换条件处理
       │
       └─ 需要下一段 → 审查 diff → 通过 → 派下一段
```

### BLD 执行纪律（v2，已确认）

1. pro 只做架构/拆解/审查/验收；flash 做小补丁
2. 大任务必须分段，每段独立可执行、可回滚
3. 卡顿闸门：3min 提示收窄，5min 中断重发，2 次卡住切 flash
4. MAIN 不代写建设代码，BLD 负责施工

---

## 9. 当前阶段不做事项

以下事项明确 **不在本次方案范围内**，后续按需评估：

1. ❌ **不建自动调度层**（无 router、无 scheduler 脚本）
2. ❌ **不建引擎健康探测**（无心跳、无自动 failover）
3. ❌ **不改 BLD 架构**（不建独立 profile、不接飞书）
4. ❌ **不做 token 精确计费系统**（依赖平台控制台）
5. ❌ **不统一三引擎 key**（CC 和 DeepSeek-TUI 共享是现状，不是目标）
6. ❌ **不做 Codex WSL 原生路径适配**（通过 symlink 绕过）
7. ❌ **不引入第四引擎**（除非业务明确需要）

---

## 10. 是否建议正式立项

**结论：建议轻量立项为 V2 制度建设 / SOP 任务；不建议立项为自动调度开发任务。**

当前只形成 BLD 多执行引擎人工调度标准，后续 3-6 个月通过真实任务验证后，再评估是否需要自动化调度。

**建议的处理方式**：

- 本文档归档到 `~/.hermes/profiles/main/regulations/` 作为参考文档
- 相关规则合并到 BLD skill 中（如有需要）
- 等 BLD 使用积累 3-6 个月经验后，再评估是否需要自动调度层立项

---

*文档结束。v1.0，2026-05-07，MAIN 落盘。*
