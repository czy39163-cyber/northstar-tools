# 来源追溯索引 — CLAUDE_CONSTRAINT_PLUGIN v1.0

> 每条约束标注出处文件、版本、原始章节。确保约束可追溯、可审计、可更新。

---

## §2 铁律

| # | 铁律 | 来源文件 | 版本 | 原始章节 |
|---|------|----------|------|----------|
| 1 | 不越权 | SOUL.md GOVERNANCE → B1 | v1.0 | 二、五大铁律 → 铁律1 |
| 2 | 不死循环 | SOUL.md GOVERNANCE → B1 | v1.0 | 二、五大铁律 → 铁律2 |
| 3 | 思维透明化 | SOUL.md GOVERNANCE → 核心铁律摘要 | v1.0 | 🔒 核心铁律摘要 #3 |
| 4 | 必须留痕 | SOUL.md GOVERNANCE → B1 | v1.0 | 二、五大铁律 → 铁律3 |
| 5 | 必须可验收 | SOUL.md GOVERNANCE → B1 | v1.0 | 二、五大铁律 → 铁律4 |
| 6 | 代码极简化 | SOUL.md GOVERNANCE → 核心铁律摘要 | v1.0 | 🔒 核心铁律摘要 #6 |
| 7 | 修改精准化 | SOUL.md GOVERNANCE → 核心铁律摘要 | v1.0 | 🔒 核心铁律摘要 #7 |
| 8 | 失败必须收敛 | SOUL.md GOVERNANCE → B1 | v1.0 | 二、五大铁律 → 铁律5 → expanded |

## §3 执行纪律

| # | 纪律 | 来源文件 | 版本 | 原始章节 |
|---|------|----------|------|----------|
| ① | task_ledger 唯一权威源 | SOUL.md GOVERNANCE → B2 | v1.2 | 二、8条执行纪律 → ① |
| ② | 执行前必查 | SOUL.md GOVERNANCE → B2 | v1.2 | 二、8条执行纪律 → ② |
| ③ | 已完成禁止重复执行 | SOUL.md GOVERNANCE → B2 | v1.2 | 二、8条执行纪律 → ③ |
| ④ | 完成必写 output_summary | SOUL.md GOVERNANCE → B2 | v1.2 | 二、8条执行纪律 → ④ |
| ⑤ | 规划前必查 | SOUL.md GOVERNANCE → B2 | v1.2 | 二、8条执行纪律 → ⑤ |
| ⑥ | 核心代码改动报 MAIN | SOUL.md GOVERNANCE → B2 | v1.2 | 二、8条执行纪律 → ⑥ |
| ⑦ | 基础设施路由 MAIN | SOUL.md GOVERNANCE → B2 | v1.2 | 二、8条执行纪律 → ⑦ |
| ⑧ | 收尾三步 | SOUL.md GOVERNANCE → B2 | v1.2 | 二、8条执行纪律 → ⑧ |

### 执行兜底（C1）

| 规则 | 来源文件 | 版本 | 原始章节 |
|------|----------|------|----------|
| 文件生成→自动升级V2 | SOUL.md GOVERNANCE → C1 | v1.0 | 四、执行兜底规则 |
| 结构化输出→自动升级V2 | SOUL.md GOVERNANCE → C1 | v1.0 | 四、执行兜底规则 |
| 核心工具调用→自动升级V2 | SOUL.md GOVERNANCE → C1 | v1.0 | 四、执行兜底规则 |

### V3 强审计

| 要求 | 来源文件 | 版本 | 原始章节 |
|------|----------|------|----------|
| 输入快照 | SOUL.md GOVERNANCE → A2 | v1.0 | 三、V3强审计额外要求 |
| 输出快照 | SOUL.md GOVERNANCE → A2 | v1.0 | 三、V3强审计额外要求 |
| 影响记录 | SOUL.md GOVERNANCE → A2 | v1.0 | 三、V3强审计额外要求 |
| 审计链完整 | SOUL.md GOVERNANCE → A2 | v1.0 | 三、V3强审计额外要求 |
| MAIN知晓 | SOUL.md GOVERNANCE → A2 | v1.0 | 三、V3强审计额外要求 |

### 失败处理

| 规则 | 来源文件 | 版本 | 原始章节 |
|------|----------|------|----------|
| 第1次失败→重试最多1次 | SOUL.md GOVERNANCE → B1 | v1.0 | 五、异常处理机制 |
| 第2次失败→上报MAIN | SOUL.md GOVERNANCE → B1 | v1.0 | 五、异常处理机制 |
| MAIN失败→上报CY | SOUL.md GOVERNANCE → B1 | v1.0 | 五、异常处理机制 |

## §4 BLD施工纪律

| 规则 | 来源文件 | 版本 | 原始章节 |
|------|----------|------|----------|
| 任务目录隔离 | bld-low-cost-workflow/SKILL.md | v1.0 | 任务专属目录隔离 |
| 不碰gateway/config/.env | bld-low-cost-workflow/SKILL.md | v1.0 | 隔离纪律 |
| 不重启服务/不改cron | bld-low-cost-workflow/SKILL.md | v1.0 | 隔离纪律 |
| 不改其他agent文件 | bld-low-cost-workflow/SKILL.md | v1.0 | 隔离纪律 |
| 安全工具类fake fixtures | bld-low-cost-workflow/SKILL.md | v1.0 | 安全工具类任务—额外约束 |
| 仅Python stdlib | bld-low-cost-workflow/SKILL.md | v1.0 | 安全工具类任务—额外约束 |
| 只读扫描 | bld-low-cost-workflow/SKILL.md | v1.0 | 安全工具类任务—额外约束 |
| 输出不含密钥原文 | bld-low-cost-workflow/SKILL.md | v1.0 | 安全工具类任务—额外约束 |
| MAIN不陪跑 | bld-low-cost-workflow/SKILL.md | v1.0 | 1. MAIN职责限制 |
| 2次失败必须停止 | bld-low-cost-workflow/SKILL.md | v1.0 | 5. 失败重试规则 |
| 禁止长链fallback | bld-low-cost-workflow/SKILL.md | v1.0 | 7. 成本控制 |

## §5 输出规范

| 规则 | 来源文件 | 版本 | 原始章节 |
|------|----------|------|----------|
| README/ACCEPTANCE/CHANGELOG | northstar-tools/CLAUDE.md | — | 输出规范 |
| B3五项一致性验收 | northstar-tools/CLAUDE.md + bld-low-cost-workflow | — | 验收标准 |
| bld_report.md格式 | bld-low-cost-workflow/SKILL.md | v1.0 | 3. 报告文件规范 |

## §6 自检清单

| 自检项 | 来源文件 | 版本 | 原始章节 |
|--------|----------|------|----------|
| ≥2种方案权衡 | SOUL.md GOVERNANCE 核心铁律#3 | v1.0 | ③思维透明化 |
| 无"将来可能用"抽象层 | SOUL.md GOVERNANCE 核心铁律#6 | v1.0 | ⑥代码极简化 |
| 检查现有skill/tool复用 | bld-low-cost-workflow SKILL.md | v1.0 | 八大铁律自检清单 |
| diff仅含目标文件 | SOUL.md GOVERNANCE 核心铁律#7 | v1.0 | ⑦修改精准化 |
| 施工前确认task_id | bld-low-cost-workflow SKILL.md | v1.0 | 八大铁律自检清单 |
| 输出有验收标准 | SOUL.md GOVERNANCE 核心铁律#5 | v1.0 | ⑤必须可验收 |
