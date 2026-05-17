# CLAUDE.md 施工约束插件 v1.0

> 独立准备包 — 仅新增文件，不覆盖现有文件、不接入运行环境、不重启

## 目的

将 Hermes 体系内已生效的八大铁律、BLD 施工纪律、SOUL.md Governance 区块**合并编译**为可直接嵌入任何 `CLAUDE.md` 的约束插件，确保所有 Claude Code 实例（尤其是 BLD/铁甲虾）在建设施工时**天然遵守**：
1. 不越权
2. 不死循环
3. 思维透明化
4. 必须留痕
5. 必须可验收
6. 代码极简化
7. 修改精准化
8. 失败必须收敛

## 包结构

```
claude-constraint-plugin/
├── README.md                                 ← 本文件
├── CLAUDE_CONSTRAINT_PLUGIN.md               ← 核心插件（可嵌入CLAUDE.md）
├── template/
│   ├── CLAUDE.md_template.md                 ← 完整 CLAUDE.md 模板（含所有约束区块）
│   ├── CLAUDE_CONSTRAINT_CHUNK.md            ← 仅约束区块（嵌现有 CLAUDE.md 用）
│   └── construction_brief_template.md        ← 施工口令模板
├── acceptance/
│   └── ACCEPTANCE.md                         ← 验收清单
└── reference/
    ├── SOURCE_INDEX.md                       ← 来源追溯索引（每条约束的出处）
    └── DIFF_ANALYSIS.md                      ← 与现有 northstar-tools/CLAUDE.md 差异分析
```

## 使用方式

### 方式 A：快速嵌入现有 CLAUDE.md

将 `template/CLAUDE_CONSTRAINT_CHUNK.md` 的内容追加到目标项目的 `CLAUDE.md` 尾部。

### 方式 B：从模板新建

复制 `template/CLAUDE.md_template.md` 作为新项目的 `CLAUDE.md`，按需填写项目特有内容（工作目录、工具链、当前阶段等）。

### 方式 C：作为约束参考文档

单独查阅 `CLAUDE_CONSTRAINT_PLUGIN.md` 作为 BLD 施工前必读约束指南。

## 设计原则

1. **不侵入现有系统** — 所有文件独立，不修改任何现有关键路径（gateway / config.yaml / .env / .bashrc / cron）
2. **不自启动** — 不注册任何 systemd service / tmux session / cron job / webhook
3. **不检查运行时状态** — 纯文本约束层，不 touch PostgreSQL / Qdrant / API
4. **来源可追溯** — 每条约束标注来源文件、版本号、原始章节
5. **可独立验证** — 验收清单可仅用 read-only 工具（grep / diff / py_compile）完成

## 依赖关系

本包引用以下上游文件（只读审计，不修改）：

| 上游文件 | 提取内容 |
|----------|----------|
| `SOUL.md (§Governance)` | B1 铁律 + B2 同步规范 + A1/A2/C1 |
| `bld-low-cost-workflow/SKILL.md` | BLD 施工七大纪律 + 自检清单 + 验收检查 |
| `northstar-tools/CLAUDE.md` | 现有 BLD 约束基线（对比分析用） |

## 版本

v1.0 / 2026-05-17
