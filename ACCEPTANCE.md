# ACCEPTANCE.md — check_stack.py v2.3 验收报告

**验收标准：** B3《工具验收全量验证规范》五项一致性检查

---

## 第一阶段验收（v2.3.0）

**验收时间：** 2026-04-30T10:05:00Z
**验收人：** MAIN（大龙虾）
**版本：** v2.3.0

### 一、文档-功能一致 ✅ PASS

| README 描述 | 代码实现 | 一致性 |
|-------------|----------|--------|
| 检查项 1：进程检查 (process) | `check_process_hermes()` — `hermes gateway status` + `pgrep` 回退 | ✅ |
| 检查项 2：端口检查 (ports) | `check_port()` — `ss`/`netstat` + TCP connect | ✅ |
| 检查项 3：配置文件检查 (config) | `check_files()` + `parse_config_content()` | ✅ |
| 检查项 4：环境变量检查 (env) | `check_env_vars()` — 4 个变量（含敏感变量脱敏） | ✅ |
| 检查项 5：HTTP 健康检查 (http) | `check_http_health()` — GET 请求 + 状态码 + 响应时间 | ✅ |
| 序号 6：结果汇总 | `build_fail_items()` + `build_recommended_actions()` + `compute_next_action()` | ✅ |

**结论：README 描述与代码实现完全一致。**

### 二、执行-输出一致 ✅ PASS

**结论：脚本执行结果在三份输出文件中完整体现。**

### 三、边界条件一致 ✅ PASS

**结论：边界条件全部有明确输出，无静默通过。**

### 四、调度机制一致 ✅ PASS

**结论：调度机制完整可用。**

### 五、MAIN 可消费一致 ✅ PASS

**结论：latest_main_summary.json 保持 MAIN 可读、字段稳定、结论明确。**

**check_stack.py v2.3 第一阶段通过基础功能一致性验收。**

---

## 第二阶段验收（v2.3.1）

**验收时间：** 2026-04-30
**验收人：** MAIN（大龙虾）
**版本：** v2.3.1

### 一、文档-功能一致 ✅ PASS

| README 描述 | 代码实现 | 一致性 |
|-------------|----------|--------|
| health_score (0-100) | `compute_health_score()` — 按类别扣分，HTTP 15分/项最重 | ✅ |
| health_level (green/yellow/red) | `compute_health_level()` — 90-100 green, 60-89 yellow, 0-59 red | ✅ |
| 历史归档 | `save_history()` — YYYYMMDDTHHMMSSZ.json 到 history/ | ✅ |
| 趋势分析 | `compute_trend()` — first_run / insufficient_history / ok | ✅ |
| 故障分类 | `classify_failures()` — new/recovered/persistent | ✅ |
| MAIN 摘要扩展 | `build_main_summary()` — 保留 11 个原有字段 + 7 个新增字段 | ✅ |
| 决策建议 | `generate_decision_hint()` — 基于健康等级+趋势+故障状态 | ✅ |

README 扣分规则表与代码 `HEALTH_DEDUCTION` 完全一致 ✅
README 健康等级范围与代码 `compute_health_level()` 完全一致 ✅
README trend.json 三种 status 状态与代码逻辑完全一致 ✅
README 新增 7 个字段名与代码输出完全一致 ✅

**结论：README 描述与代码实现完全一致。**

### 二、执行-输出一致 ✅ PASS

| 输出文件 | 验证项 | 结果 |
|----------|--------|------|
| `latest_report.json` | 包含 health_score, health_level, health_info 字段 | ✅ |
| `latest_summary.txt` | 包含 Health 行、New failures、Recovered、Trend、Decision hint | ✅ |
| `latest_main_summary.json` | 原有 11 字段 + 新增 7 字段（共 18 字段） | ✅ |
| `history/` 目录 | 包含 YYYYMMDDTHHMMSSZ.json 格式归档文件 | ✅ |
| `trend.json` | 包含 status, trend_direction, comparison, runs | ✅ |

**结论：所有输出文件包含预期的新增字段，原有字段保持不变。**

### 三、边界条件一致 ✅ PASS

| 场景 | 预期行为 | 结果 |
|------|----------|------|
| 无历史记录（首次运行） | trend.json: `{"status": "first_run", ...}` | ✅ |
| 仅 1 条历史记录 | trend.json: `{"status": "insufficient_history", ...}` | ✅ |
| 2+ 条历史记录 | trend.json: `{"status": "ok", "trend_direction": "...", ...}` | ✅ |
| 首次运行故障分类 | 所有 fail_items → new_fail_items, recovered/persistent = [] | ✅ |
| 全部通过 | health_score=100, health_level=green | ✅ |
| 全部失败 | health_score >= 0, health_level=red | ✅ |
| `--only` 单项 | 健康分仅基于该项 fail_items 计算 | ✅ |
| 原有 11 字段兼容 | latest_main_summary.json 仍包含 tool_name, version 等 11 字段 | ✅ |

**结论：边界条件全部有明确输出，无静默通过。**

### 四、调度机制一致 ✅ PASS

| 检查项 | 结果 |
|--------|------|
| `run_check_stack.sh` 是否存在 | ✅ |
| 是否可执行 | ✅ |
| 是否真实调用 check_stack.py | ✅ |
| 版本一致性 | ✅ VERSION="2.3.1" |
| 历史归档 Step 3 | ✅ 复制到 history/ |
| 输出文件生成 | ✅ 5 份文件全部生成（latest_report / latest_summary / latest_main_summary / history / trend） |
| 退出码传递 | ✅ 业务退出码 0/1 透传，脚本错误 2 中断 |
| 参数透传 | ✅ "$@" 透传到所有 python3 调用 |

**结论：调度机制完整可用。**

### 五、MAIN 可消费一致 ✅ PASS

| 检查项 | 结果 |
|--------|------|
| `latest_main_summary.json` 是否存在 | ✅ |
| 是否合法 JSON | ✅ |
| 原有字段数量 | ✅ 11 个字段保持不变 |
| 新增字段数量 | ✅ 7 个新增字段 |
| 总字段数量 | ✅ 18 个字段 |
| 字段名稳定 | ✅ 全部 18 个字段名固定 |
| 新增字段类型稳定 | ✅ health_score(int), health_level(str), new_fail_items(array), recovered_items(array), persistent_fail_items(array), trend_summary(str), main_decision_hint(str) |
| 可直接解析 | ✅ MAIN 可用 `json.load()` 一步消费 |

**结论：latest_main_summary.json 保持向下兼容，新增字段 schema 稳定。**

---

## 第二阶段总验收结论

| # | 检查项 | 结果 |
|---|--------|------|
| 1 | 文档-功能一致 | ✅ PASS |
| 2 | 执行-输出一致 | ✅ PASS |
| 3 | 边界条件一致 | ✅ PASS |
| 4 | 调度机制一致 | ✅ PASS |
| 5 | MAIN 可消费一致 | ✅ PASS |

**check_stack.py v2.3.1 第二阶段通过健康分级与趋势分析一致性验收。**

---

## 本次变更清单（v2.3.1 第二阶段）

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `check_stack.py` | 修改 | VERSION "2.3.0" → "2.3.1"；新增 health_score/health_level 计算、故障分类、历史归档、趋势分析、MAIN 摘要扩展 |
| `README.md` | 更新 | 新增健康分/健康等级/故障分类/历史归档/趋势分析/MAIN 扩展字段说明；更新 JSON 输出示例 |
| `run_check_stack.sh` | 更新 | 新增 Step 3 历史归档（复制到 history/）、输出 history/trend 文件路径 |
| `ACCEPTANCE.md` | 更新 | 新增第二阶段五项验收条款 |
| `CHANGELOG.md` | 更新 | 记录 v2.3.1 变更 |

## 本阶段不做

1. ~~main_stack_digest.py~~ ✅ TSK-014811
2. ~~stack_watchdog.sh~~ ✅ TSK-014813
3. warning_report / blocked_report / recovered_report
4. 飞书推送
5. 自动修改 task_ledger

---

## main_stack_digest.py 验收（TSK-014811）

**验收时间：** 2026-04-30
**验收人：** MAIN（大龙虾）
**版本：** v1.0

### 一、文档-功能一致 ✅ PASS

| 功能 | 代码实现 | 一致性 |
|------|----------|--------|
| 读取 latest_main_summary.json | `load_json()` + `generate()` | ✅ |
| 读取 trend.json | `--with-trend` / `--all` 参数 | ✅ |
| 读取 latest_report.json | `--with-report` / `--all` 参数 | ✅ |
| 中文 Markdown 输出 | `generate()` 返回格式化字符串 | ✅ |
| 健康分/趋势/恢复/故障显示 | 各 section 函数 | ✅ |
| 环境变量脱敏 | 只显示 set/missing，不打印值 | ✅ |

### 二、执行-输出一致 ✅ PASS

`--all` 模式输出完整中文摘要，与健康分/趋势/故障状态完全对应。

### 三、边界条件一致 ✅ PASS

| 场景 | 结果 |
|------|------|
| JSON 文件不存在 | 打印 WARN，不崩溃 |
| JSON 解析失败 | 打印 WARN，不崩溃 |
| 空数组（无故障/恢复项） | 显示 "(本轮无)" |

### 四、调度机制一致 ✅ PASS

`--summary-only` / `--with-trend` / `--with-report` / `--all` 四种模式均可正常执行。

### 五、MAIN 可消费一致 ✅ PASS

输出为中文 Markdown，可直接粘贴飞书或 MAIN 阅读。

**结论：main_stack_digest.py v1.0 通过基础功能一致性验收（非完整生产验收）。**

---

## main_stack_digest.py 文件落盘补丁验收（TSK-014812）

**验收时间：** 2026-04-30
**验收人：** MAIN（大龙虾）

### 验证项

| 检查项 | 结果 |
|--------|------|
| stdout 模式向后兼容 | ✅ `--all` 输出与修改前一致 |
| `--save` 文件落盘 | ✅ 三个 latest_digest + history 归档均生成 |
| `latest_digest.md` 与 stdout 一致 | ✅ diff identical |
| `latest_digest.txt` 无 Markdown/emoji | ✅ `**` 标记数=0 |
| `latest_digest_feishu.txt` 保留 emoji 无 `**` | ✅ emoji=7, `**`=0 |
| `--no-stdout` 无终端输出 | ✅ stdout 为空 |
| 无 API Key 泄露 | ✅ 三个文件均通过 |

**结论：main_stack_digest.py 文件落盘补丁通过基础功能一致性验收（非完整生产验收）。**

---

## stack_watchdog.py 验收（TSK-014813）

**验收时间：** 2026-04-30
**验收人：** MAIN（大龙虾）
**版本：** v1.0

### 一、文档-功能一致 ✅ PASS

| 功能 | 代码实现 | 一致性 |
|------|----------|--------|
| 连续 yellow/red 计数 | trend.json runs 数组连续统计 | ✅ |
| persistent_fail 持续判断 | watchdog_state.json 跨次对比 | ✅ |
| recovered 检测 | latest_main_summary.json recovered_items | ✅ |
| 7 种 watchdog_status | 优先级判断逻辑 | ✅ |
| first_run 边界 | is_first_run + previous_status=null | ✅ |
| missing_input 边界 | input_status 逐项标记 | ✅ |

### 二、执行-输出一致 ✅ PASS

| 输出文件 | 验证项 | 结果 |
|----------|--------|------|
| watchdog_state.json | 13 个字段全部存在且类型正确 | ✅ |
| latest_watchdog_summary.md | 中文 Markdown 格式 | ✅ |
| latest_watchdog_summary.txt | 纯文本格式 | ✅ |
| history/ | 时间戳归档文件 | ✅ |
| `--status` | 仅输出状态字符串 | ✅ |

### 三、边界条件一致 ✅ PASS

| 场景 | 预期 | 结果 |
|------|------|------|
| green 正常（当前数据） | recovery_detected（因 recovered_items 非空） | ✅ |
| 无历史状态（首次运行） | is_first_run=true, previous_status=None | ✅ |
| 所有输入缺失 | watchdog_status=missing_input | ✅ |

### 测试场景覆盖

| 场景 | 验证方式 | 结果 |
|------|----------|------|
| green 正常 | 当前数据：health_level=green, recovered_items=4 项 | ✅ recovery_detected |
| 连续 yellow | trend.json 含 5 次 yellow runs | ✅ 检测到连续 yellow 计数（当前 green 仅 1 次不触发 warning_ready，需 ≥3 次） |
| 连续 red / persistent fail | 无当前数据，代码逻辑已实现连续 2 次 red → blocked_ready, persistent ≥3 次 → persistent_issue | ✅ 逻辑就绪 |

### 四、调度机制一致 ✅ PASS

`--run` / `--status` / `--output-dir` 三种参数模式均可正常执行。

### 五、MAIN 可消费一致 ✅ PASS

watchdog_state.json 可用 `json.load()` 一步消费；summary.md 为中文 Markdown 可直接粘贴飞书。

### 观察项

Claude Code 通过 wrapper 执行时偶发 exit 124（超时）或 exit 130（中断），但目标文件均已完整生成，登记为非阻塞观察项。

**结论：stack_watchdog.py v1.0 通过基础功能一致性验收（非完整生产验收）。**

---

## v2.3.2 Feishu 诊断增强补丁验收

**验收时间：** 2026-05-03  
**验收人：** MAIN（大龙虾）  
**版本：** v2.3.2

### 一、文档-功能一致 ✅ PASS

| README / CHANGELOG 描述 | 代码实现 | 一致性 |
|---|---|---|
| Feishu 专项诊断 | `FEISHU_HEALTH_URLS` / `FEISHU_HTTP_TIMEOUT` / `FEISHU_REQUIRED_ACCOUNT_KEYS` | ✅ |
| `check_feishu_http()` | 检测 Feishu bot ping 端点连通性（8 秒超时） | ✅ |
| `build_feishu_fail_items()` | 专门处理 Feishu 失败项分类（ping / config / bot_identity） | ✅ |
| `--only feishu` CLI 支持 | 独立运行 Feishu 诊断 | ✅ |
| `HEALTH_DEDUCTION["feishu"] = 15` | Feishu 失败扣分权重 | ✅ |
| `feishu_checks` 顶层字段 | 全量 JSON 报告新增 | ✅ |

**结论：** `README.md` / `CHANGELOG.md` 描述与代码实现一致。

---

### 二、执行-输出一致 ✅ PASS

| 输出文件 | 验证项 | 结果 |
|---|---|---|
| `latest_report.json` | 包含 `feishu_checks` 字段 | ✅ |
| `latest_summary.txt` | 展示 Feishu 检查结果 | ✅ |
| `latest_main_summary.json` | 保持 MAIN 可消费格式，含 Feishu 诊断相关字段 | ✅ |
| `trend.json` | 趋势分析正常更新 | ✅ |
| `history/` 目录 | 包含 `YYYYMMDDTHHMMSSZ.json` 格式归档文件 | ✅ |

**结论：** 所有输出文件均包含预期新增字段，原有字段保持不变。

---

### 三、边界条件一致 ✅ PASS

| 场景 | 预期行为 | 结果 |
|---|---|---|
| `--only feishu` | 仅运行 Feishu 诊断，输出 `feishu_checks` | ✅ |
| Feishu ping 失败（404） | 归类为 `feishu` 类别，不误判为其他业务失败 | ✅ |
| 无 Feishu 账户配置 | `fail_items` 中出现 `feishu.config` 项 | ✅ |
| 网络不可达 vs 业务错误 | `check_feishu_http()` 区分 `network_reachable` 与 `status_code` | ✅ |

**结论：** 边界条件均有明确输出，无静默通过。

---

### 四、调度机制一致 ✅ PASS

| 检查项 | 结果 |
|---|---|
| `run_check_stack.sh` 是否存在 | ✅ |
| 是否可执行 | ✅ |
| 是否支持参数透传 | ✅ |
| 版本一致性 | ✅ `VERSION="2.3.2"` |
| 历史归档 Step 3 | ✅ 复制到 `history/` |
| 输出文件生成 | ✅ 5 份文件全部生成（`latest_report` / `latest_summary` / `latest_main_summary` / `history` / `trend`） |
| 退出码传递 | ✅ 业务退出码 `0/1` 透传，脚本错误 `2` 中断 |

**结论：** 调度机制完整可用。

---

### 五、MAIN 可消费一致 ✅ PASS

| 检查项 | 结果 |
|---|---|
| `latest_main_summary.json` 是否存在 | ✅ |
| 是否为合法 JSON | ✅ |
| 原有字段数量 | ✅ 11 个字段保持不变 |
| 新增字段数量 | ✅ 7 个新增字段（如 `health_score` 等） |
| 总字段数量 | ✅ 18 个字段 |
| 字段名稳定 | ✅ 全部 18 个字段名固定 |
| 新增字段类型稳定 | ✅ `health_score(int)`、`health_level(str)`、`new_fail_items(array)`、`recovered_items(array)`、`persistent_fail_items(array)`、`trend_summary(str)`、`main_decision_hint(str)` |
| 可直接解析 | ✅ MAIN 可用 `json.load()` 一步消费 |

**结论：** `latest_main_summary.json` 保持向下兼容，新增字段 schema 稳定。

---

## v2.3.2 验收总结论

| # | 检查项 | 结果 |
|---|---|---|
| 1 | 文档-功能一致 | ✅ PASS |
| 2 | 执行-输出一致 | ✅ PASS |
| 3 | 边界条件一致 | ✅ PASS |
| 4 | 调度机制一致 | ✅ PASS |
| 5 | MAIN 可消费一致 | ✅ PASS |

**结论：** `check_stack.py v2.3.2` Feishu 诊断增强补丁通过基础功能一致性验收。  
本轮已完成代码、文档、输出、调度与 MAIN 摘要链路的一致性验证，补丁功能完整落地。

---

## 验收说明

本轮验收确认补丁功能通过，但**当前环境健康状态未通过**。本次运行发现以下环境问题：

1. `ANTHROPIC_BASE_URL` 未设置  
2. `ANTHROPIC_MODEL` 未设置  
3. `CLAUDE_CODE_SUBAGENT_MODEL` 未设置  
4. `ANTHROPIC_AUTH_TOKEN` 未设置  
5. OpenClaw 配置中未检测到有效 Feishu accounts：
   - `config.yaml`：无 Feishu accounts
   - `config.json`：无 Feishu accounts
   - `openclaw.json`：Feishu accounts 字段存在结构不符合脚本预期，需按标准数组格式修正

上述问题属于**环境真实异常被脚本成功识别**，**不构成 v2.3.2 补丁功能失败**。

**后续处理：** 这两类问题不按"主链环境待修复"处理，转为独立任务《check_stack 检查域分层修正（主链 / 通道基础设施 / 特种支路）》：

**1. `ANTHROPIC_*` 4 项 → 条件检查项**
- BLD 固定走 DeepSeek 兼容端点，不接 Anthropic
- 从 mainline 全局必检项调整为条件检查项
- 仅当 provider_mode=anthropic 时检查；当前 deepseek_compatible 模式下标记为 skipped / not_applicable

**2. OpenClaw Feishu accounts → 通道基础设施层长期纳管**
- 口径升级：不按"可忽略观察项"处理，纳入 channel_infra（通道基础设施层）长期保留与长期纳管
- 不是北极星主链硬失败项，但也不是可长期忽略的问题
- 应独立作为通道层健康进行正式检查、正式留痕、正式修复
- FIN 飞书支路明确保留；后续企微机器人按同一"通道基础设施层"长期建设与纳管

**3. check_stack 检查域分层方向**

| 域 | 名称 | 说明 |
|---|---|---|
| mainline | 主链核心健康 | Hermes gateway / agent / PostgreSQL / 端口 / 配置 |
| channel_infra | 通道基础设施 | OpenClaw Feishu / 后续企微等通道健康 |
| special_branch | 特种支路健康 | FIN 等特种支路 |

修复后执行以下命令进行复测：

```bash
bash run_check_stack.sh
python3 check_stack.py --only feishu --json
python3 check_stack.py --summary-json
python3 check_stack.py --summary-text
```

---

## v2.4.0 检查域分层架构验收

**验收时间：** 2026-05-04
**验收人：** MAIN（大龙虾）
**版本：** v2.4.0

### 一、文档-功能一致 ✅ PASS

| README / CHANGELOG 描述 | 代码实现 | 一致性 |
|---|---|---|
| 三层检查域：mainline / channel_infra / special_branch | `CHECK_DOMAINS` 常量（L53-66） | ✅ |
| mainline 包含 process, ports, config, env, http | `CHECK_DOMAINS["mainline"]["checks"]` | ✅ |
| channel_infra 包含 feishu | `CHECK_DOMAINS["channel_infra"]["checks"]` | ✅ |
| special_branch 预留（空） | `CHECK_DOMAINS["special_branch"]["checks"] = []` | ✅ |
| 顶层 health_score 仅反映 mainline | L1209-1210：`health_score = mainline_health["health_score"]` | ✅ |
| `--only` 支持域名称 | `parse_args()` choices 含 mainline/channel_infra/special_branch | ✅ |
| 域过滤逻辑 | L996-997：`enabled_categories = set(CHECK_DOMAINS[only_filter]["checks"])` | ✅ |
| `compute_domain_health()` per-domain 独立健康分 | L672-686 | ✅ |
| `--json` 全量报告含 `domains` 字段 | L1291：`"domains": domains` | ✅ |
| `--summary-json` 含 `domains` 字段 | L939：`base["domains"] = results.get("domains", {})` | ✅ |
| `detect_provider_mode()` 条件环境变量检查 | L126-143 | ✅ |
| ANTHROPIC_* 条件检查（anthropic 模式 required，其他 INFO） | L1036-1056 | ✅ |
| feishu 扣分权重 15 | `HEALTH_DEDUCTION["feishu"] = 15` | ✅ |

**结论：README / CHANGELOG 描述与代码实现完全一致。**

### 二、执行-输出一致 ✅ PASS

| 命令 | 退出码 | 验证项 | 结果 |
|------|--------|--------|------|
| `python3 check_stack.py --json` | 1（有真实环境故障） | 全量报告含 domains 字段 | ✅ |
| `--only mainline --summary-json` | 1 | checks_run=[process,ports,config,env,http]，domains.mainline 反映主链 | ✅ |
| `--only channel_infra --summary-json` | 1 | checks_run=[feishu]，domains.channel_infra 反映通道层 | ✅ |
| `--only special_branch --summary-json` | 0 | checks_run=[]，空域 ALL_OK | ✅ |

| 验证场景 | 结果 |
|----------|------|
| 全量模式 domains.mainline.health_score=100, channel_infra.health_score=55 | ✅ 顶层 health_score=100（仅 mainline） |
| `--only mainline` 不产生 feishu fail_items | ✅ |
| `--only channel_infra` fail_items 全部为 feishu category | ✅ |
| `--only special_branch` 无检查项、无 fail_items | ✅ |

**结论：四种执行模式的输出均与文档描述完全一致。**

### 三、边界条件一致 ✅ PASS

| 场景 | 预期行为 | 结果 |
|------|----------|------|
| `--only mainline` 时 channel_infra 的 feishu 被跳过 | skipped_items 记录 | ✅ |
| `--only channel_infra` 时 mainline 检查被跳过 | skipped_items 记录 | ✅ |
| special_branch 域 checks=[] | health_score=100, health_level=green, fail_items=[] | ✅ |
| 非 anthropic 模式下 ANTHROPIC_* 标记为 INFO | `[INFO]` 标记显示，不计入 fail | ✅ |
| 全量模式 fail_items 跨域统计正确 | mainline 0 项 + channel_infra 3 项 = 总 3 项 | ✅ |

**结论：边界条件均有明确输出，无静默通过。**

### 四、调度机制一致 ✅ PASS

| 检查项 | 结果 |
|--------|------|
| `run_check_stack.sh` 是否存在 | ✅ |
| 是否可执行 | ✅ |
| `--only` 域名称透传正确 | ✅ |
| 版本一致性 | ✅ VERSION="2.4.0" |

**结论：调度机制完整可用。**

### 五、MAIN 可消费一致 ✅ PASS

| 检查项 | 结果 |
|--------|------|
| `latest_main_summary.json` 含 `domains` 字段 | ✅ |
| `domains` 结构：mainline/channel_infra/special_branch 各含 health_score/health_level/fail_items | ✅ |
| 原有 18 字段保持不变 | ✅ |
| `domains` 为新增第 19 个字段 | ✅ |
| 可直接 `json.load()` 消费 | ✅ |

**结论：MAIN 摘要保持向下兼容，domains 字段 schema 稳定。**

---

## v2.4.0 验收总结论

| # | 检查项 | 结果 |
|---|--------|------|
| 1 | 文档-功能一致 | ✅ PASS |
| 2 | 执行-输出一致 | ✅ PASS |
| 3 | 边界条件一致 | ✅ PASS |
| 4 | 调度机制一致 | ✅ PASS |
| 5 | MAIN 可消费一致 | ✅ PASS |

**结论：check_stack.py v2.4.0 检查域分层架构通过基础功能一致性验收。**

---

## 本阶段不做

1. ~~main_stack_digest.py~~ ✅ TSK-014811
2. ~~stack_watchdog.sh~~ ✅ TSK-014813
3. ~~Feishu 诊断增强~~ ✅ v2.3.2
4. ~~检查域分层~~ ✅ v2.4.0
5. warning_report / blocked_report / recovered_report
6. 飞书推送
7. 自动修改 task_ledger