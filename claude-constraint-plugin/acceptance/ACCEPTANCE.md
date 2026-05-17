# ACCEPTANCE.md — CLAUDE.md 施工约束插件 v1.0 验收清单

> 验证方式：read-only（仅 grep / diff / py_compile / ls），不写库、不调 API、不改配置
> 验收日期：2026-05-17

---

## 0. 包完整性验收

| # | 验收项 | 预期 | 验证方式 |
|---|--------|------|----------|
| P1 | 目录结构完整 | 如下 6 个文件均存在 | `ls -laR` |
| P2 | 不覆盖现有文件 | 无文件写入 northstar-tools/ 当前任何文件 | `diff` 不冲突 |
| P3 | 不写入关键路径 | 不碰 gateway/config.yaml/.env/cron | `grep` 关键路径 |

## 1. 文件完整性

| # | 文件 | 预期 | 验证方式 |
|---|------|------|----------|
| F1 | `README.md` | 包概述，含目的、结构、使用方式 | `head -5` 含标题 |
| F2 | `CLAUDE_CONSTRAINT_PLUGIN.md` | 核心约束，覆盖 §1-§7 | 含 7 个 § 标题 |
| F3 | `template/CLAUDE.md_template.md` | 完整模板 | 含铁律、红线、自检 |
| F4 | `template/CLAUDE_CONSTRAINT_CHUNK.md` | 嵌入区块 | 含八大铁律 + 八条纪律 |
| F5 | `template/construction_brief_template.md` | 施工口令模板 | 含 8 个 sections |
| F6 | `reference/SOURCE_INDEX.md` | 来源追溯 | 每条约束可追溯 |
| F7 | `reference/DIFF_ANALYSIS.md` | 差异分析 | 含与原 CLAUDE.md 对比 |

## 2. 内容完整性

| # | 验收项 | 预期 | 验证方式 |
|---|--------|------|----------|
| C1 | 八大铁律完整 | 8 条（不越权/不死循环/思维透明/留痕/验收/精简/精准/收敛） | `grep` 8 个编号 |
| C2 | 八条执行纪律完整 | 8 条（①-⑧） | `grep` ①-⑧ |
| C3 | BLD 红线完整 | 不碰 gateway/config.yaml/.env/cron/跨agent | `grep` 红线 |
| C4 | 自检清单完整 | 6 项自检（③⑥⑥⑦④⑤） | `grep` 6 个 □ |
| C5 | 失败处理完整 | 1次重试/2次停止/MAIN升级 | `grep` 失败 |
| C6 | 输出规范完整 | B3 五项 | `grep` B3 |
| C7 | 禁止操作清单 | ✅ 至少 12 条 | `grep` ❌ 计数 |

## 3. 差异分析完整性

| # | 验收项 | 预期 | 验证方式 |
|---|--------|------|----------|
| D1 | 对比现有 northstar-tools/CLAUDE.md | 列出差异项 | 阅读 DIFF_ANALYSIS.md |
| D2 | 合并建议 | 给出嵌入 vs 替换建议 | 阅读 DIFF_ANALYSIS.md |
| D3 | 不重复项标记 | 标记已在原 CLAUDE.md 中的约束 | 阅读 DIFF_ANALYSIS.md |

## 4. 安全合规

| # | 验收项 | 预期 | 验证方式 |
|---|--------|------|----------|
| S1 | 无 API key/token/secret | 文件中无明文凭证 | `grep -rn 'sk-\|api_key\|token\|password\|secret' --include='*.md'` |
| S2 | 无生产路径修改指令 | 无 gateway/config.yaml/.env 修改 | `grep` 关键路径 |
| S3 | 无自启动/自注册 | 无 systemd/cron/tmux/webhook 注册 | `grep` |
| S4 | 无运行时状态检查 | 无 PostgreSQL/Qdrant/API 调用 | `grep` |

---

## 验收结论

| 区块 | 状态 |
|------|------|
| 包完整性 | □ 通过 / □ 不通过 |
| 文件完整性 | □ 通过 / □ 不通过 |
| 内容完整性 | □ 通过 / □ 不通过 |
| 差异分析 | □ 通过 / □ 不通过 |
| 安全合规 | □ 通过 / □ 不通过 |

**总体验收：** □ 全部通过 / □ 存在失败项
