# Composio 集成中间件 — Hermes 数据采集层设计方案

## 概述

**Composio** 是 AI agent 集成中间件（28K⭐, MIT SDK + 闭源 SaaS），支持 1000+ 平台一键 OAuth 连接。  
本方案采用 **路线 B（数据采集层）**：Composio 同步外部平台数据 → Chunk → 注入 Qdrant VDB，供 Hermes agent 通过 `vdb_search` 检索。**不修改 agent 核心架构，不依赖 Composio 做实时 tool call。**

## 架构总览

```
┌─────────────────────────────────────────────────────┐
│                   Hermes 生态                         │
│                                                       │
│  ┌──────────┐   vdb_search    ┌──────────────────┐   │
│  │ Hermes   │◄───────────────│  Qdrant VDB       │   │
│  │ Agent    │                 │  (ns_global_know  │   │
│  │ (OPS/    │                 │   ledge /          │   │
│  │  DSG/    │                 │   ns_resources)    │   │
│  │  SALES)  │                 └──────────┬───────┘   │
│  └──────────┘                            │           │
│                                          │ write     │
│                                 ┌────────▼───────┐   │
│                                 │  Composio      │   │
│                                 │  Fetch Worker  │   │
│                                 │  (Hermes cron  │   │
│                                 │  调度)          │   │
│                                 └────────┬───────┘   │
│                                          │           │
│                                          │ HTTPS     │
│                                 ┌────────▼───────┐   │
│                                 │  Composio      │   │
│                                 │  Cloud (SaaS)  │   │
│                                 │  后端           │   │
│                                 └────────┬───────┘   │
│                                          │           │
│                                          │ OAuth     │
│                                 ┌────────▼───────┐   │
│                                 │  外部平台       │   │
│                                 │  (Gmail/GitHub │   │
│                                 │   /Notion/...) │   │
│                                 └────────────────┘   │
└─────────────────────────────────────────────────────┘
```

## 核心原则

1. **数据采集层** — Composio 仅做数据同步，不做实时 tool call 注入
2. **VDB 作为数据枢纽** — 所有外部数据经 chunk 处理后写入 Qdrant
3. **不修改 agent 核心架构** — 现有 agent 无需感知 Composio 存在
4. **调度可控** — 通过 Hermes cron 控制采集频率（20min/1h/1d）
5. **降级安全** — Composio 不可用时，agent 仍可用已有 VDB 数据

## 数据流

```
Composio API Fetch
    ↓
原始数据（JSON/Markdown/Email/...）
    ↓
Chunk 处理器（≤3K token Markdown chunk）
    ↓
chunk 元数据标注（platform/source/time/type）
    ↓
Qdrant 写入（ns_global_knowledge / ns_resources）
    ↓
Hermes agent vdb_search 检索
```

## 调度策略

| 平台类型 | 推荐频率 | 说明 |
|---------|---------|------|
| Gmail/IMAP 邮件 | 每 20min | 实时性要求高 |
| GitHub Issues/PR | 每 1h | 日间活跃 |
| Notion/Calendar | 每 1h | 变化频率中等 |
| 文档类（Wiki/Drive） | 每 1d | 低频变化 |
| CRM（Stripe/Salesforce） | 每 30min | 交易数据敏感 |

## VDB Schema 映射

```python
vector_entry = {
    "content": chunk_text,          # ≤3K token Markdown
    "namespace": "ns_global_knowledge",  # 或 ns_resources
    "metadata": {
        "source": "composio",
        "platform": "gmail",         # 数据源平台
        "time": "2026-05-17T10:00:00Z",  # 采集时间
        "type": "email",             # 数据类型
        "composio_connection_id": "...",  # Composio 连接 ID
        "chunk_index": 0,            # 分片序号
        "total_chunks": 3,           # 总分片数
    }
}
```

## 实施步骤

### Phase 0：CY 授权（阻塞点）

| 事项 | 说明 | 预计耗时 |
|------|------|---------|
| ① 注册 Composio Free tier 账号 | 用哪个邮箱？ | 10min |
| ② 生成 COMPOSIO_API_KEY | 从 Dashboard 获取 | 1min |
| ③ 纳管密钥到 Hermes ~/.hermes/credentials/ | 由 MAIN 操作 | 5min |
| ④ 选择首个 OAuth 连接平台 | 推荐: Gmail (只读) | 5min |
| ⑤ 确认数据范围 | 只读/范围限制 | 10min |

### Phase 1：最小可行性验证（CY 授权后当天可完成）

1. `pip install composio`（Python SDK 安装）
2. Composio CLI login（API Key 配置）
3. OAuth 连接首个平台（如 Gmail 只读）
4. 编写采集脚本：fetch → chunk → VDB write
5. 手动跑通第一次采集
6. 验证 Hermes agent 可通过 `vdb_search` 检索到数据

### Phase 2：生产化

1. 封装为 Hermes cron 定时任务
2. 添加多平台支持（GitHub / Notion / Calendar）
3. 搭建降级策略（采集失败时通知 MAIN）
4. 监控：采集成功率、VDB 写入完整性、API 额度消耗
5. B3 五项一致性验收

## 风险与缓解

| 风险 | 等级 | 缓解措施 |
|------|------|---------|
| Composio 后端闭源 | ⚠️ 中 | 数据采集层策略，不依赖实时 tool call |
| OAuth Token 托管在云 | ⚠️ 中 | 仅连接只读权限平台 |
| 第三方服务不可用 | ⚠️ 中 | VDB 缓存机制，降级为已有数据 |
| 定价变化 | ⚠️ 低 | Free tier 20K calls/月够用；$29/200K 可接受 |
| API 限流 | ⚠️ 低 | 控制采集频率，20min+ 间隔 |
| SDK 许可证 (MIT) | ✅ 无 | 与 Hermes 无冲突 |

## 激活条件

以下任一触发时，正式上线此能力：
- SALES 需要一键连接客户 CRM 数据源
- 手动管理外部 API key 成为明显痛点（当前 3-4 个 provider 尚未到达痛点）
- CY 手动指令激活

## 引用

- Composio 官网: https://composio.dev
- Composio GitHub: https://github.com/ComposioHQ/composio
- Composio Python SDK: pip install composio
- Priors: vector_main (05-16/05-17 评估记录), 候选技能清单(飞书多维表格)
