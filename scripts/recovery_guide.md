# 龙虾系统恢复指南

**适用场景**: 硬盘坏死、Windows 崩溃、更换电脑  
**目标**: 2 小时内恢复完整系统  

---

## 前置条件

- [ ] 新电脑已装 WSL2 (Ubuntu 24.04)
- [ ] GitHub SSH key 已配置 (czy39163@gmail.com)
- [ ] Seafile 已同步到本地
- [ ] GPG 私钥已导入
- [ ] PostgreSQL 16 + Qdrant 已安装 (apt)

---

## 恢复步骤

### Step 1: 克隆代码

```bash
# northstar-tools (控制器、bridge、check_stack)
cd ~ && git clone git@github.com:czy39163/northstar-tools.git

# hermes-agent (从上游克隆，应用补丁)
cd ~ && git clone https://github.com/nicholasgriffintn/hermes-agent.git
cd hermes-agent && git checkout <last_known_commit>

# 应用我们的补丁
cp /mnt/f/Seafile/龙虾备份/hermes_patches_最新/feishu.py ~/hermes-agent/gateway/platforms/
cp /mnt/f/Seafile/龙虾备份/hermes_patches_最新/weixin.py ~/hermes-agent/gateway/platforms/
cp /mnt/f/Seafile/龙虾备份/hermes_patches_最新/gpt-loop.sh ~/.hermes/scripts/

# 安装 Python 依赖
cd ~/hermes-agent && pip install -r requirements.txt
pip install websocket-client pg8000  # 额外依赖
```

### Step 2: 恢复配置

```bash
# 解密配置包
gpg --decrypt /mnt/f/Seafile/龙虾备份/configs_最新.tar.gpg | tar xf - -C ~/

# 验证 API key 可读
head -1 ~/.hermes/profiles/main/.env  # 应显示 API_SERVER_KEY=...
```

### Step 3: 恢复数据库

```bash
# PostgreSQL
createdb CY_Database
psql -U hermes_writer CY_Database < /mnt/f/Seafile/龙虾备份/task_ledger_最新.sql

# Qdrant (如有导出)
# Qdrant 启动后自动可用，无需恢复（向量可重建）
```

### Step 4: 启动服务

```bash
# 启动 7 个 gateway (通过 tmux)
cd ~/.hermes/scripts && ./hermes-gateways-tmux.sh start

# 验证
curl http://127.0.0.1:18642/health  # MAIN
curl http://127.0.0.1:18645/health  # DSG

# 启动 Bridge (如需要 CDP 模式)
API_SERVER_KEY=main-secret python3 ~/northstar-tools/browser-ext/bridge/bridge_server.py &
```

### Step 5: 验证

```bash
# 测试 GPT-Loop 链路
cd ~/northstar-tools
python3 gpt_loop_controller.py start "验证测试。1轮：MAIN回复OK"
python3 gpt_loop_controller.py status

# 测试环境巡检
python3 check_stack.py --json
```

### Step 6: Chrome 扩展

- 加载扩展: `F:\功能知识库\05-铁甲虾\gpt-loop_v1.0`
- CCPC360 Token Sync: 从备份重新安装

---

## 验证检查清单

- [ ] 7 个 gateway 全部 running
- [ ] MAIN API 响应正常
- [ ] GPT-Loop controller 可启动、可完成 1 轮
- [ ] check_stack 报告 green
- [ ] Feishu 消息可达
- [ ] `/task` 命令可在飞书触发

---

## GPG 私钥恢复

如果新电脑没有 GPG 私钥：

```bash
# 从旧电脑导出私钥（在旧电脑上）
gpg --export-secret-keys czy39163@gmail.com > private.key

# 导入到新电脑
gpg --import private.key
```

**注意**: GPG 私钥文件 (`private.key`) 需保存在安全位置（物理 U 盘或密码管理器），不能和加密文件放在一起。

---

## 已知依赖

| 软件 | 安装方式 | 用途 |
|------|----------|------|
| Python 3.12 | WSL 自带 | 所有工具 |
| PostgreSQL 16 | `apt install postgresql` | task_ledger |
| Qdrant | Docker 或 binary | 向量记忆 |
| pip packages | `pip install websocket-client pg8000 ...` | controller |
| Chrome | Windows 安装 | 扩展宿主 |
| Seafile | Windows 客户端 | 文件同步 |
