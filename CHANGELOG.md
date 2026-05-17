# Changelog

## 2026-05-04 — v2.4.0 检查域分层架构

- **check_stack.py**
  - 新增三层检查域架构：mainline / channel_infra / special_branch
  - 新增 `CHECK_DOMAINS` 常量和 `CATEGORY_DOMAIN_MAP` 自动映射
  - 新增 `compute_domain_health()` 函数，per-domain 独立计算健康分
  - 新增 `detect_provider_mode()` 函数，根据 Hermes config 动态检测 provider 模式
  - `collect_results()` 返回值新增 `domains` 字段（每域 health_score/health_level/fail_items）
  - 顶层 `health_score/health_level` 仅反映 mainline 域
  - ANTHROPIC_* 环境变量改为条件检查（anthropic 模式 required，其他模式 info 级别）
  - `build_fail_items()` 新增 `enabled_categories` 参数，支持 `--only` 域过滤
  - `--only` 参数扩展支持域名称：mainline / channel_infra / special_branch
  - `build_main_summary()` 新增 `domains` 字段输出
  - `_show_env()` 新增 `[INFO]` 标记显示
  - VERSION "2.3.2" → "2.4.0"

- **README.md**
  - 新增"检查域分层"章节
  - 更新 `--only` 参数文档（域过滤）
  - 更新环境变量检查说明（条件检查）

- **验收标准**
  - mainline 域 health_score 不受 channel_infra 故障影响
  - `--only mainline` 不产生 feishu fail_items
  - 顶层 fail_items 与各域 fail_items 统计一致
  - `--summary-json` 和 `--json` 均包含 `domains` 字段

## 2026-05-02 — v2.3.2 Feishu 诊断增强补丁

- **check_stack.py**
  - 修复 `check_feishu_http()`: 区分 HTTP 状态码和网络错误，只有真正网络不可达才算 ping fail
  - 增强 `parse_config_content()`: 支持 `.env` 文件解析和 `${VAR_NAME}` 变量展开
  - 新增变量解析失败检测：`${...}` 无法解析到值时标记为 fail
  - 优化失败项判断：app_ticket 在长连接模式下可降级为 warning
  - 添加 `python-dotenv` 依赖支持（可选）
  - VERSION "2.3.1" → "2.3.2"

- **README.md**
  - 更新版本号到 v2.3.2
  - 新增 Feishu 诊断增强说明

## 2026-05-02 — v2.3.2 Feishu 专项诊断

- **check_stack.py**
  - 新增 Feishu 专项诊断常量：`FEISHU_HEALTH_URLS`、`FEISHU_HTTP_TIMEOUT`、`FEISHU_REQUIRED_ACCOUNT_KEYS`、`FEISHU_BOT_IDENTITY_FIELDS`
  - 新增 `check_feishu_http()`: 检测 Feishu bot ping 端点连通性（8秒超时）
  - 扩展 `parse_config_content()`: 解析 OpenClaw Feishu accounts，检查 `app_id`/`app_secret`/`app_ticket`/`bot_open_id` 状态
  - 新增 `build_feishu_fail_items()`: 专门处理 Feishu 失败项分类（ping / config / bot_identity）
  - 新增 `--only feishu` CLI 支持，独立运行 Feishu 诊断
  - 新增 `HEALTH_DEDUCTION["feishu"] = 15`: Feishu 失败扣分权重
  - 扩展 `build_recommended_actions()`: 添加 Feishu 专用修复建议
  - 新增 `_show_feishu()`: 文本输出中显示 Feishu 诊断结果
  - 全量 JSON 报告新增 `feishu_checks` 顶层字段

- **README.md**
  - 新增"Feishu 诊断"章节，说明专项检查目的和注意事项
  - 新增 `--only feishu --json` 使用示例
  - 更新 `--only` 参数说明，包含 `feishu` 选项
  - 更新 JSON 输出示例，包含 `feishu_checks` 字段

- **验收标准**
  - Feishu 诊断失败项归类为 `feishu` 类别，避免误判为 FIN 业务失败
  - 网络连通性 / bot 身份问题与 FIN agent 业务能力分离

## 2026-04-30 — v2.3.1 第二阶段：健康分级与趋势分析

- **check_stack.py**
  - VERSION "2.3.0" → "2.3.1"
  - 新增 `compute_health_score()`: 0-100 健康分，按失败类别差异化扣分（HTTP 15分 > process 12分 > config 8分 > env 5分）
  - 新增 `compute_health_level()`: 基于 health_score 生成 green/yellow/red 等级
  - 新增 `classify_failures()`: 对比当前与历史 fail_items，识别 new/recovered/persistent
  - 新增 `save_history()`: 自动归档完整报告到 history/ 目录（YYYYMMDDTHHMMSSZ.json）
  - 新增 `compute_trend()`: 生成趋势分析（first_run / insufficient_history / ok）
  - 新增 `generate_decision_hint()`: 基于健康等级+趋势+故障状态生成一句话决策建议
  - `build_main_summary()` 扩展：保留原有 11 字段，新增 7 个 health/trend 字段
  - `build_main_summary_text()` 扩展：新增健康分、故障分类、趋势、决策建议输出
  - 全量 JSON 报告新增 health_score, health_level, health_info 顶层字段

- **run_check_stack.sh**
  - 新增 Step 3: 复制完整报告到 history/ 目录
  - 更新输出信息：显示 history 和 trend 文件路径

- **README.md**
  - 新增"健康分与健康等级"章节
  - 新增"故障分类"章节
  - 新增"历史归档"章节
  - 新增"趋势分析"章节
  - 新增"MAIN 摘要扩展字段"章节
  - 更新 JSON 输出示例（含 v2.3.1 新字段）
  - 更新边界条件表（含首次运行/历史不足场景）
  - 更新输出文件说明表（含 history/ 和 trend.json）
  - 新增 `--only feishu` Feishu 诊断说明

## 2026-04-30 — v2.3.0 第一阶段：基础功能

- **check_stack.py**
  - VERSION "2.2.0" → "2.3.0"
  - 新增 HTTP 健康检查（`check_http_health()`）
  - 新增 `--summary-json` / `--summary-text` 输出模式
  - 新增 `--output` 写入文件
  - 新增 `build_fail_items()` / `build_recommended_actions()` / `compute_next_action()`
  - 新增 `build_main_summary()` 11 字段 MAIN 可消费摘要
  - 修复：--only 参数、退出码语义

- **README.md** 重写，修复文档-功能不一致
- **run_check_stack.sh** 修复退出码逻辑

## 2026-04-30 — 初始版本

- **check_stack.py** 创建
  - Hermes gateway 进程检查（`hermes gateway status` + `pgrep` 回退）
  - 端口连通性检查（本地监听 + TCP connect，兼容 WSL→Windows）

## 2026-04-30 — v2.3.0 第一阶段：基础功能

- **check_stack.py**
  - VERSION "2.2.0" → "2.3.0"
  - 新增 HTTP 健康检查（`check_http_health()`）
  - 新增 `--summary-json` / `--summary-text` 输出模式
  - 新增 `--output` 写入文件
  - 新增 `build_fail_items()` / `build_recommended_actions()` / `compute_next_action()`
  - 新增 `build_main_summary()` 11 字段 MAIN 可消费摘要
  - 修复：--only 参数、退出码语义

- **README.md** 重写，修复文档-功能不一致
- **run_check_stack.sh** 修复退出码逻辑

## 2026-04-30 — 初始版本

- **check_stack.py** 创建
  - Hermes gateway 进程检查（`hermes gateway status` + `pgrep` 回退）
  - 端口连通性检查（本地监听 + TCP connect，兼容 WSL→Windows）
  - OpenClaw 配置文件检查（Linux 本地 + Windows 映射路径，yaml/yml/json）
  - 环境变量检查（含敏感变量脱敏输出）
  - 结构化分区输出（进程 / 端口 / 配置 / 环境变量 / 总结）

这是 Claude Code 方案 B 跑通后的第一个正式工具。
