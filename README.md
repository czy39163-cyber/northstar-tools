# northstar-tools

环境巡检工具集，用于日常快速确认本地开发栈 (WSL2 + Windows) 的健康状态。

## check_stack.py (v2.4.0)

一键巡检脚本，覆盖以下 6 项检查：

| 序号 | 检查项 | 说明 |
|------|--------|------|
| 1 | 进程检查 | Hermes gateway 是否在运行（优先 `hermes gateway status`，回退 `pgrep`） |
| 2 | 端口检查 | 关键端口是否可连通（先查本地监听 `ss`/`netstat`，再尝试 TCP connect，兼容 WSL→Windows 场景） |
| 3 | 配置文件检查 | OpenClaw 配置文件是否存在（覆盖 Linux 本地路径 + Windows 映射路径，兼容 yaml/yml/json） |
| 4 | 环境变量检查 | 根据 provider_mode 动态检查：anthropic 模式检查 ANTHROPIC_* 系列，其他模式标记为 INFO（不扣分） |
| 5 | HTTP 健康检查 | 对预设 URL 列表执行 HTTP GET，验证服务可达性与响应状态码 |
| 6 | 结果汇总 | 汇总通过/未通过/警告项数、失败明细、建议动作、下一步行动 |

> **注意：** 序号 6 不是独立检查项，而是对前 5 项结果的汇总输出。脚本实际执行的独立检查为 **5 项**（process / ports / config / env / http）。

## 检查域分层（v2.4.0 新增）

所有检查项按三层域分类：

| 域 | 说明 | 包含的检查项 |
|----|------|-------------|
| mainline | 主链核心健康 | process, ports, config, env, http |
| channel_infra | 通道基础设施健康 | feishu |
| special_branch | 特种支路健康 | （预留） |

- **顶层 health_score 仅反映 mainline 域**，channel_infra / special_branch 的健康状态独立计算
- `--only` 参数支持域过滤：`--only mainline` / `--only channel_infra` / `--only special_branch`
- `--json` 全量报告新增 `domains` 字段，包含每域的 health_score、health_level、fail_items
- `--summary-json` 紧凑摘要也包含 `domains` 字段

## 健康分与健康等级（v2.3.1 新增）

每次巡检自动计算 **health_score**（0-100）和 **health_level**：

| 等级 | 分数范围 | 含义 |
|------|----------|------|
| green | 90-100 | 环境健康 |
| yellow | 60-89 | 存在非关键问题 |
| red | 0-59 | 严重故障 |

**扣分规则：**

| 失败类别 | 每项扣分 | 说明 |
|----------|----------|------|
| http | 15 | HTTP 超时/错误扣分最重（通常意味着服务不可用） |
| feishu | 15 | 飞书诊断失败（网络不通或 bot 身份异常） |
| process | 12 | 核心进程不可用 |
| config | 8 | 配置文件缺失 |
| env | 5 | 环境变量未设置 |

## 故障分类（v2.3.1 新增）

通过对比当前运行与上一次历史记录，自动识别故障变化：

| 字段 | 说明 |
|------|------|
| `new_fail_items` | 本次新增故障（上次没有的） |
| `recovered_items` | 本次恢复项（上次有但本次没有的） |
| `persistent_fail_items` | 持续存在故障（两次都有） |

> 首次运行时：所有 fail_items 归入 new_fail_items，recovered/persistent 为空数组。

## 历史归档（v2.3.1 新增）

每次通过 `run_check_stack.sh` 运行时，自动将完整报告归档到 `reports/check_stack/history/` 目录。

- 文件名格式：`YYYYMMDDTHHMMSSZ.json`（ISO 时间戳）
- 内容：与 `latest_report.json` 完全相同的完整 JSON 报告副本
- 历史记录用于趋势分析和故障对比

## 趋势分析（v2.3.1 新增）

自动生成 `reports/check_stack/trend.json`，记录最近 N 次运行的健康数据：

| 字段 | 说明 |
|------|------|
| `status` | `first_run`（首次）、`insufficient_history`（仅1条）、`ok`（正常） |
| `trend_direction` | `改善` / `稳定` / `恶化` |
| `comparison` | 最近两次运行的详细对比 |
| `runs` | 历史运行条目列表（health_score, health_level, ok, fail, run_at） |

边界情况：
- 无历史数据：`{"status": "first_run", "message": "...", "runs": [...]}` — 不会报错
- 仅1条历史：`{"status": "insufficient_history", "message": "...", "runs": [...]}` — 不会报错

## MAIN 摘要扩展字段（v2.3.1 新增）

`latest_main_summary.json` 在保持原有 11 个字段完全不变的基础上，新增 7 个字段：

| 新增字段 | 类型 | 说明 |
|----------|------|------|
| `health_score` | int | 0-100 健康分 |
| `health_level` | string | green / yellow / red |
| `new_fail_items` | array | 本次新增故障 |
| `recovered_items` | array | 本次恢复项 |
| `persistent_fail_items` | array | 持续故障 |
| `trend_summary` | string | 改善/稳定/恶化/首次运行/数据不足 |
| `main_decision_hint` | string | 一句话决策建议 |

原有 11 个字段保持完全兼容：
`tool_name`, `version`, `status`, `exit_code`, `ok`, `fail`, `fail_items`, `warnings`, `checks_run`, `next_action`, `recommended_actions`

## 运行方法

### 直接运行

```bash
# 文本模式（默认，运行全部 5 项检查）
python3 check_stack.py

# JSON 输出（全量报告）
python3 check_stack.py --json

额外参数可透传，例如：`bash run_check_stack.sh --only http`

# Feishu 专项诊断
python3 check_stack.py --only feishu --json

# 详细模式
python3 check_stack.py --verbose

# 自定义参数
python3 check_stack.py --windows-user Administrator --ports 18642,18648,8644,18789
```

### 通过 run_check_stack.sh 运行（推荐）

```bash
bash run_check_stack.sh
```

该脚本自动执行以下步骤：

1. 运行 `check_stack.py --json`，生成带时间戳的完整报告 → `reports/check_stack/<TIMESTAMP>.json`
2. 复制为 `reports/check_stack/latest_report.json`
3. 归档到 `reports/check_stack/history/<TIMESTAMP>.json`
4. 生成 `reports/check_stack/latest_summary.txt`（人类可读文本）
5. 生成 `reports/check_stack/latest_main_summary.json`（MAIN 可消费 JSON，含健康分/趋势字段）

额外参数可透传，例如：`bash run_check_stack.sh --only http`

## 命令行参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--json` | 输出 JSON 格式全量报告 | (off) |
| `--verbose` | 详细输出 | (off) |
| `--windows-user` | Windows 用户名（拼接 WSL 路径） | Administrator |
| `--ports` | 逗号分隔的端口列表 | 18642,18648,8644,18789,22,443,3000,5000,8000,8080,8443 |
| `--only` | 仅运行指定检查类别（支持 process / ports / config / env / http / feishu / all / mainline / channel_infra / special_branch） | (全部) |
| `--output` | 将输出写入文件（配合 `--json` / `--summary-json` / `--summary-text`） | (stdout) |
| `--summary-json` | 输出 MAIN 可消费的紧凑 JSON 摘要 | (off) |
| `--summary-text` | 输出人类可读的文本摘要 | (off) |

`--only` 可选值：`process` | `ports` | `config` | `env` | `http` | `feishu` | `all` | `mainline` | `channel_infra` | `special_branch`

## 退出码

| 退出码 | 含义 |
|--------|------|
| 0 | 全部检查通过 (ALL_OK) |
| 1 | 存在失败项 (HAS_FAILURES) |
| 2 | 脚本自身异常 (SCRIPT_ERROR) |

## Feishu 诊断

`--only feishu` 专项检查 Feishu bot 身份和网络连通性：

- **网络连通性**：ping `https://open.feishu.cn/open-apis/bot/v1/openclaw_bot/ping`（8秒超时）
- **OpenClaw 配置**：解析 Feishu accounts，检查 `app_id` / `app_secret` / `app_ticket` / bot `open_id` 状态
- **失败分类**：Feishu 失败项归类为 `feishu` 类别，避免误判为 FIN 业务失败

**注意**：Feishu 诊断失败表示基础设施问题（网络/bot身份），而非 FIN agent 业务能力问题。

## JSON 输出结构

### 全量报告（`--json`）

```json
{
  "meta": {
    "tool_name": "check_stack",
    "version": "2.4.0",
    "run_at": "2026-04-30T09:59:53Z",
    "hostname": "CY",
    "platform": "Linux",
    "windows_user": "Administrator",
    "cwd": "/home/cy/northstar-tools"
  },
  "process": { "name": "hermes", "running": true, "method": "...", "detail": "..." },
  "ports": [
    { "port": 18642, "status": "listening", "detail": "..." },
    { "port": 22, "status": "not available", "detail": "port 22 not available" }
  ],
  "config_files": {
    "openclaw": { "exists": true, "checked_count": 24, "found": ["..."], "content": [...] }
  },
  "env_vars": {
    "required": [ { "name": "ANTHROPIC_BASE_URL", "set": true, "display": "..." } ],
    "sensitive": [ { "name": "ANTHROPIC_AUTH_TOKEN", "set": true, "display": "已设置" } ]
  },
  "http_checks": [
    { "url": "http://127.0.0.1:18642/health", "success": true, "status_code": 200, "time_ms": 23, "error": null }
  ],
  "feishu_checks": [
    { "url": "https://open.feishu.cn/open-apis/bot/v1/openclaw_bot/ping", "success": false, "status_code": null, "time_ms": 310, "error": "HTTP Error 404: Not Found", "category": "feishu" }
  ],
  "fail_items": [
    { "category": "feishu", "name": "feishu.ping", "detail": "HTTP Error 404: Not Found" },
    { "category": "feishu", "name": "feishu.config", "detail": "config.yaml has no Feishu accounts" }
  ],
  "recommended_actions": [ "Check network connectivity to open.feishu.cn and Feishu bot ping endpoint" ],
  "next_action": "investigate_failures",
  "warnings": [],
  "summary": {
    "ok": 5,
    "fail": 1,
    "total": 6,
    "status": "HAS_FAILURES",
    "exit_code": 1,
    "checks_run": ["process", "ports", "config", "env", "http"]
  },
  "health_score": 80,
  "health_level": "yellow",
  "health_info": {
    "health_score": 80,
    "health_level": "yellow",
    "new_fail_items": [...],
    "recovered_items": [...],
    "persistent_fail_items": [...],
    "trend_summary": "稳定",
    "main_decision_hint": "..."
  },
  "domains": {
    "mainline": { "health_score": 100, "health_level": "green", "fail_items": [] },
    "channel_infra": { "health_score": 40, "health_level": "red", "fail_items": [...] },
    "special_branch": { "health_score": 100, "health_level": "green", "fail_items": [] }
  }
}
```

### MAIN 摘要（`--summary-json`）

```json
{
  "tool_name": "check_stack",
  "version": "2.4.0",
  "status": "HAS_FAILURES",
  "exit_code": 1,
  "ok": 8,
  "fail": 4,
  "fail_items": [ { "category": "...", "name": "...", "detail": "..." } ],
  "warnings": [],
  "checks_run": ["process", "ports", "config", "env", "http"],
  "next_action": "investigate_failures",
  "recommended_actions": ["..."],
  "health_score": 100,
  "health_level": "green",
  "new_fail_items": [],
  "recovered_items": [],
  "persistent_fail_items": [ { "category": "...", "name": "...", "detail": "..." } ],
  "trend_summary": "稳定",
  "main_decision_hint": "存在 4 项持续故障，建议安排修复。",
  "domains": {
    "mainline": { "health_score": 100, "health_level": "green", "fail_items": [] },
    "channel_infra": { "health_score": 40, "health_level": "red", "fail_items": [...] },
    "special_branch": { "health_score": 100, "health_level": "green", "fail_items": [] }
  }
}
```

### 趋势文件（`trend.json`）

```json
{
  "status": "ok",
  "trend_direction": "稳定",
  "comparison": {
    "previous_run_at": "2026-04-30T10:02:46Z",
    "previous_health_score": 80,
    "previous_health_level": "yellow",
    "current_health_score": 80,
    "current_health_level": "yellow",
    "trend_direction": "稳定"
  },
  "runs": [
    { "run_at": "...", "ok": 8, "fail": 4, "health_score": 80, "health_level": "yellow" },
    { "run_at": "...", "ok": 8, "fail": 4, "health_score": 80, "health_level": "yellow" }
  ]
}
```

## 边界条件处理

| 场景 | 行为 |
|------|------|
| Hermes gateway 未启动 | 进程检查返回 `running: false`，计入失败 |
| 端口不可访问 | 标记为 `not available`，**不**计入失败（仅 info 级别） |
| OpenClaw 配置不存在 | 配置文件检查返回 `exists: false`，计入失败 |
| 环境变量未设置 | 标记为 `未设置`，计入失败 |
| HTTP 健康检查失败 | 返回错误信息，计入失败，扣分最重（15分/项） |
| 脚本自身异常 | 返回 exit code 2，JSON 中 `status` 为 `SCRIPT_ERROR` |
| 敏感环境变量 | 值不会出现在输出中，仅显示"已设置"/"未设置" |
| 无历史记录（首次运行） | trend.json 输出 `first_run`，所有 fail_items 归入 new_fail_items |
| 仅1条历史记录 | trend.json 输出 `insufficient_history`，不报错 |

## 输出文件说明（run_check_stack.sh）

| 文件 | 说明 |
|------|------|
| `reports/check_stack/<TIMESTAMP>.json` | 带时间戳的完整 JSON 报告（归档） |
| `reports/check_stack/latest_report.json` | 最新完整 JSON 报告（覆盖更新） |
| `reports/check_stack/latest_summary.txt` | 最新人类可读文本摘要（含健康分、故障分类） |
| `reports/check_stack/latest_main_summary.json` | 最新 MAIN 可消费 JSON 摘要（18 字段） |
| `reports/check_stack/history/<TIMESTAMP>.json` | 历史归档报告（完整副本） |
| `reports/check_stack/trend.json` | 趋势分析文件 |

## Digest 输出文件说明（main_stack_digest.py）

`main_stack_digest.py` 读取 check_stack JSON 产物，生成 MAIN / 飞书可读的中文巡检摘要。

| 文件 | 格式 | 用途 |
|------|------|------|
| `reports/check_stack/digest/latest_digest.md` | 完整 Markdown | 标准摘要，与 `--all` stdout 输出一致 |
| `reports/check_stack/digest/latest_digest.txt` | 纯文本（无 Markdown/emoji） | 纯文本场景、日志归档 |
| `reports/check_stack/digest/latest_digest_feishu.txt` | 紧凑文本（保留 emoji，无 Markdown） | 飞书消息直接粘贴 |
| `reports/check_stack/digest/history/<TIMESTAMP>_digest.md` | Markdown | 历史归档副本 |

使用方式：
```bash
# 仅 stdout（默认，向后兼容）
python3 main_stack_digest.py --all

# 文件落盘 + stdout
python3 main_stack_digest.py --all --save

# 仅落盘，不打印到终端
python3 main_stack_digest.py --all --save --no-stdout

# 自定义输出目录
python3 main_stack_digest.py --all --save --output-dir /tmp/my-digest/
```

## stack_watchdog.py（连续异常判断层）

读取 check_stack + digest 产物，判断连续异常、持续故障、恢复状态，生成 watchdog 状态文件。

### 输入文件

| 文件 | 必需 | 说明 |
|------|------|------|
| `reports/check_stack/latest_main_summary.json` | 是 | 主摘要（health_score, fail_items, recovered_items 等） |
| `reports/check_stack/trend.json` | 是 | 趋势数据（runs 数组，用于连续计数） |
| `reports/check_stack/digest/latest_digest.md` | 否 | digest Markdown（用于输入状态检查） |
| `reports/check_stack/digest/latest_digest_feishu.txt` | 否 | digest 飞书版（用于输入状态检查） |

### 输出文件

| 文件 | 说明 |
|------|------|
| `reports/check_stack/watchdog/watchdog_state.json` | 当前 watchdog 状态（含历史对比） |
| `reports/check_stack/watchdog/latest_watchdog_summary.md` | MAIN 可读 Markdown 摘要 |
| `reports/check_stack/watchdog/latest_watchdog_summary.txt` | 纯文本摘要 |
| `reports/check_stack/watchdog/history/<TIMESTAMP>_watchdog.json` | 历史归档 |

### 触发规则（按优先级从高到低）

| 优先级 | 条件 | watchdog_status |
|--------|------|-----------------|
| 1 | 连续 2 次 red | `blocked_ready` |
| 2 | 连续 3 次 yellow | `warning_ready` |
| 3 | persistent_fail_items 连续 3 次 | `persistent_issue` |
| 4 | recovered_items 非空 | `recovery_detected` |
| 5 | green 且无 persistent | `normal` |
| 6 | 其他 | `monitoring` |
| - | 所有输入缺失 | `missing_input` |

### 状态定义

| watchdog_status | 含义 | 下一步动作 |
|-----------------|------|-----------|
| `normal` | 一切正常 | 无 |
| `monitoring` | 无明确判断 | 继续观察 |
| `recovery_detected` | 检测到恢复 | 记录，后续可生成 recovered_report |
| `persistent_issue` | 持续故障 | 后续可生成 warning_report |
| `warning_ready` | 连续黄色告警 | 后续可生成 warning_report |
| `blocked_ready` | 连续红色阻塞 | 后续可生成 blocked_report |
| `missing_input` | 输入数据缺失 | 需排查数据源 |

### 使用方式

```bash
# 执行一次判断（默认）
python3 stack_watchdog.py --run

# 仅输出状态（用于脚本判断）
python3 stack_watchdog.py --status

# 自定义输出目录
python3 stack_watchdog.py --run --output-dir /tmp/watchdog/
```

### 本阶段边界
- 只生成判断结果，不生成正式 warning/blocked/recovered report
- 不写 task_ledger / 不推飞书 / 不自动修复
