#!/usr/bin/env python3
"""
Composio 集成中间件 — 缺 Key 检测 Dry-Run 脚本
================================================
功能：检查 Composio 集成所需的全部前置条件，输出详细状态报告。
     纯 dry-run 模式：不写真实 key、不联网、不改生产配置。

安全约束：
  - 禁止读取或输出任何真实 API Key / Token / Secret
  - 禁止连接 Composio 云服务
  - 禁止修改生产配置文件
  - 仅读取 .env.example（模板）和 Hermes credentials 路径是否存在

输出格式：JOSN（供 MAIN 消费）+ 终端彩色摘要
"""

import json
import os
import sys
from pathlib import Path

# ── 配置 ──────────────────────────────────────────────────
WORK_DIR = Path("/home/cy/northstar-tools/composio-prep")
ENV_EXAMPLE = WORK_DIR / ".env.example"
HERMES_CRED_DIR = Path.home() / ".hermes" / "credentials"
HERMES_PROFILES_DIR = Path.home() / ".hermes" / "profiles"
COMPOSIO_PIP_CHECK = False  # 不联网，不安装

# ── 结果容器 ──────────────────────────────────────────────
results = {
    "check_name": "Composio 集成中间件 — 缺 Key 检测 Dry-Run",
    "check_version": "1.0.0",
    "check_time": None,
    "summary": {
        "total": 0,
        "pass": 0,
        "fail": 0,
        "blocked": 0,
    },
    "checks": [],
    "verdict": None,  # 最终判定
    "blocked_pending_CY_auth": True,
}


def add_check(name: str, status: str, detail: str, is_blocking: bool = False):
    """添加一项检查结果"""
    entry = {
        "name": name,
        "status": status,  # PASS / FAIL / BLOCKED / SKIP
        "detail": detail,
        "is_blocking": is_blocking,
    }
    results["checks"].append(entry)
    results["summary"]["total"] += 1
    if status == "PASS":
        results["summary"]["pass"] += 1
    elif status == "FAIL":
        results["summary"]["fail"] += 1
        if is_blocking:
            results["summary"]["blocked"] += 1


def check_env_example():
    """检查 .env.example 是否存在，以及关键变量是否已由 CY 授权填充"""
    if not ENV_EXAMPLE.exists():
        add_check("env.example 文件存在", "FAIL", f"文件不存在: {ENV_EXAMPLE}", is_blocking=True)
        return

    content = ENV_EXAMPLE.read_text(encoding="utf-8")

    # 检查模板完整性
    required_keys = ["COMPOSIO_API_KEY", "COMPOSIO_USER_ID"]
    missing_keys = [k for k in required_keys if f"{k}=" not in content]
    if missing_keys:
        add_check("env.example 模板键完整性", "FAIL",
                  f"缺失关键占位：{', '.join(missing_keys)}", is_blocking=True)
        return

    # 检查关键变量的填充状态：
    # 如果 COMPOSIO_API_KEY 后有值（≠空或注释行），说明已授权
    api_key_line = None
    for line in content.splitlines():
        if line.startswith("COMPOSIO_API_KEY="):
            api_key_line = line
            break

    if api_key_line is None:
        add_check("COMPOSIO_API_KEY 状态", "FAIL", "未找到 COMPOSIO_API_KEY 行", is_blocking=True)
        return

    # 提取等号后的值（去除引号和空白）
    raw_val = api_key_line.split("=", 1)[1].strip().strip('"').strip("'")

    if raw_val and not raw_val.startswith("#"):
        add_check("COMPOSIO_API_KEY 已授权", "PASS", f"API Key 已配置，长度: {len(raw_val)} 字符")
    else:
        add_check("COMPOSIO_API_KEY 待授权", "FAIL",
                  "API Key 为空 — 等待 CY 注册 Composio Free tier 账号后填充", is_blocking=True)

    # 检查 COMPOSIO_USER_ID
    uid_line = None
    for line in content.splitlines():
        if line.startswith("COMPOSIO_USER_ID="):
            uid_line = line
            break
    if uid_line:
        uid_val = uid_line.split("=", 1)[1].strip().strip('"').strip("'")
        if uid_val and not uid_val.startswith("#"):
            add_check("COMPOSIO_USER_ID 已配置", "PASS", f"User ID: {uid_val}")
        else:
            add_check("COMPOSIO_USER_ID 待配置", "FAIL",
                      "User ID 为空 — 注册账号后自动生成", is_blocking=True)
    else:
        add_check("COMPOSIO_USER_ID 待配置", "FAIL",
                  "User ID 未找到", is_blocking=True)


def check_hermes_credentials():
    """检查 Hermes credentials 目录是否存在，是否有 composio 相关的配置"""
    if not HERMES_CRED_DIR.exists():
        add_check("Hermes credentials 目录", "PASS",
                  "路径不存在（首次安装正常）")
        return

    existing_files = list(HERMES_CRED_DIR.glob("*composio*"))
    config_files = list(HERMES_CRED_DIR.glob("*.yaml")) + list(HERMES_CRED_DIR.glob("*.yml"))

    if existing_files:
        add_check("Composio 密钥文件", "FAIL",
                  f"发现 {len(existing_files)} 个 composio 相关文件（不应存在，需人工确认是否遗留）",
                  is_blocking=True)
    else:
        add_check("Composio 密钥文件", "PASS",
                  "credentials 目录下无 composio 密钥文件（尚未配置）")

    # 检查是否有其他 credentials 配置（仅检查是否存在文件）
    if config_files:
        add_check("Credentials 配置完整性", "PASS",
                  f"credentials 目录存在 {len(config_files)} 个配置文件，系统正常")
    else:
        add_check("Credentials 配置完整性", "PASS",
                  "credentials 目录为空（首次安装正常）")


def check_python_env():
    """检查 Python 环境和系统依赖（不联网安装）"""
    try:
        import importlib.util
        spec = importlib.util.find_spec("composio")
        if spec is not None:
            # 已安装 composio — 读取版本
            try:
                import composio
                ver = getattr(composio, "__version__", "unknown")
                add_check("Composio Python SDK 已安装", "PASS",
                          f"版本: {ver} (路径: {spec.origin})")
            except ImportError:
                add_check("Composio Python SDK 已安装", "PASS",
                          f"路径: {spec.origin} (版本获取失败)")
        else:
            add_check("Composio Python SDK 未安装", "FAIL",
                      "pip install composio 尚未执行", is_blocking=False)
    except Exception as e:
        add_check("Python 环境检查", "FAIL", f"检查异常: {e}", is_blocking=False)


def check_blocking_conditions():
    """汇总阻塞条件"""
    blocked_reasons = []

    # 检查是否有 FAIL + is_blocking 项
    for c in results["checks"]:
        if c["status"] == "FAIL" and c["is_blocking"]:
            blocked_reasons.append(c["name"])

    if blocked_reasons:
        results["verdict"] = "BLOCKED"
        results["blocked_pending_CY_auth"] = True
        results["blocked_reasons"] = blocked_reasons
    else:
        results["verdict"] = "DRY_RUN_PASS"
        results["blocked_pending_CY_auth"] = False


def print_report():
    """打印终端报告"""
    sep = "=" * 70
    print(f"\n{sep}")
    print(f"  {results['check_name']}")
    print(f"  版本: {results['check_version']}")
    print(f"{sep}")
    print(f"  摘要: {results['summary']['total']} 项检查 "
          f"| ✅ {results['summary']['pass']} PASS "
          f"| ❌ {results['summary']['fail']} FAIL "
          f"| 🔒 {results['summary']['blocked']} BLOCKED")
    print(f"{sep}\n")

    for c in results["checks"]:
        icon = {"PASS": "✅", "FAIL": "❌", "BLOCKED": "🔒", "SKIP": "⏭️"}.get(c["status"], "❓")
        blocking = " [阻塞]" if c["is_blocking"] and c["status"] == "FAIL" else ""
        print(f"  {icon} {c['name']}{blocking}")
        print(f"     {c['detail']}")
        print()

    print(f"{sep}")
    print(f"  判定: {results['verdict']}")
    print(f"  阻塞等待 CY 授权: {'是' if results['blocked_pending_CY_auth'] else '否'}")
    print(f"{sep}\n")

    if results["blocked_pending_CY_auth"]:
        print("  ⚠️  当前状态: BLOCKED — 需要 CY 完成以下授权:")
        for reason in results.get("blocked_reasons", []):
            print(f"    🔴 {reason}")
        print()
        print("  📝 继续推进前置条件:")
        print("    1. CY 注册 Composio Free tier 账号")
        print("    2. CY 生成 COMPOSIO_API_KEY")
        print("    3. CY 授权 OAuth 首个平台连接")
        print("    4. 将 API Key 纳入 Hermes credentials 管理")
    else:
        print("  ✅ Dry-run 检查通过 — 所有前置条件已满足")
    print()


def save_report():
    """保存 JSON 报告到文件"""
    import datetime
    results["check_time"] = datetime.datetime.now().isoformat()

    report_path = WORK_DIR / "dryrun_report.json"
    report_path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"  📄 报告已保存: {report_path}")


def main():
    check_env_example()
    check_hermes_credentials()
    check_python_env()
    check_blocking_conditions()
    print_report()
    save_report()

    # 返回退出码：0 = dry-run 通过（不阻塞），1 = 阻塞
    return 0 if not results["blocked_pending_CY_auth"] else 1


if __name__ == "__main__":
    sys.exit(main())
