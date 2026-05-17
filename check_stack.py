#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Environment stack check script v2.4.0 — scheduled + MAIN summary + health/trend + domain architecture + Feishu enhanced."""

import argparse
import copy
import glob
import json
import os
import platform
import shutil
import socket as socket_mod
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

try:
    from dotenv import load_dotenv
    DOTENV_AVAILABLE = True
except ImportError:
    DOTENV_AVAILABLE = False

# ============================================================
# 配置区 — 按需修改
# ============================================================

# 默认端口列表（可通过 --ports 覆盖）
DEFAULT_PORTS = [
    # 当前环境关键端口
    18642,
    18648,
    8644,
    18789,
    # 通用端口
    22,
    443,
    3000,
    5000,
    8000,
    8080,
    8443,
]

# 默认 Windows 用户名（可通过 --windows-user 覆盖）
DEFAULT_WINDOWS_USER = "Administrator"

VERSION = "2.4.0"

# 检查域定义
CHECK_DOMAINS = {
    "mainline": {
        "description": "主链核心健康",
        "checks": ["process", "ports", "config", "env", "http"],
    },
    "channel_infra": {
        "description": "通道基础设施健康",
        "checks": ["feishu"],
    },
    "special_branch": {
        "description": "特种支路健康",
        "checks": [],  # 预留：FIN 飞书支路等
    },
}

# 检查类别 → 域映射（由 CHECK_DOMAINS 自动生成）
CATEGORY_DOMAIN_MAP: dict[str, str] = {}
for _domain_name, _domain_def in CHECK_DOMAINS.items():
    for _check in _domain_def["checks"]:
        CATEGORY_DOMAIN_MAP[_check] = _domain_name

# HTTP 健康检查 URL 列表
HTTP_HEALTH_URLS = [
    "http://127.0.0.1:18642/health",
]

# Feishu 诊断 URL / 超时设置
FEISHU_HEALTH_URLS = [
    "https://open.feishu.cn/open-apis/bot/v1/openclaw_bot/ping",
]
FEISHU_HTTP_TIMEOUT = 8.0
FEISHU_REQUIRED_ACCOUNT_KEYS = ["app_id", "app_secret", "app_ticket"]
FEISHU_BOT_IDENTITY_FIELDS = ["bot_open_id", "open_id", "bot_id"]

# 报告输出目录（相对于脚本所在目录的父目录，或绝对路径）
REPORTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports", "check_stack")

# 历史归档目录
HISTORY_DIR = os.path.join(REPORTS_DIR, "history")

# 健康分扣分权重：HTTP 失败扣分更重
HEALTH_DEDUCTION = {
    "http":   15,   # HTTP 超时/错误 — 每项扣 15 分
    "feishu": 15,   # Feishu bot ping / identity 问题
    "process": 12,  # 进程不可用
    "config": 8,    # 配置文件缺失
    "env":     5,   # 环境变量未设置 — 每项扣 5 分
}

# ============================================================
# 工具函数
# ============================================================

def build_config_paths(windows_user: str) -> list[str]:
    """Build OpenClaw config candidate paths from Linux + Windows mappings."""
    paths = []
    # Linux 本地
    for _prefix in [
        os.path.expanduser("~/.openclaw"),
        os.path.expanduser("~/.config/openclaw"),
    ]:
        for _name in ["config", "openclaw"]:
            for _ext in [".yaml", ".yml", ".json"]:
                paths.append(os.path.join(_prefix, _name + _ext))
    # Windows 映射路径（WSL）
    _win_base = f"/mnt/c/Users/{windows_user}"
    for _sub in [".openclaw", ".config/openclaw"]:
        for _name in ["config", "openclaw"]:
            for _ext in [".yaml", ".yml", ".json"]:
                paths.append(os.path.join(_win_base, _sub, _name + _ext))
    return paths


def detect_provider_mode() -> str:
    """Detect provider mode. Checks HERMES_PROVIDER_MODE env var, then Hermes config, defaults to deepseek_compatible."""
    env_mode = os.environ.get("HERMES_PROVIDER_MODE")
    if env_mode:
        return env_mode
    config_path = os.path.expanduser("~/.hermes/profiles/main/config.yaml")
    try:
        if os.path.exists(config_path):
            import yaml
            with open(config_path, "r") as f:
                config = yaml.safe_load(f)
            if isinstance(config, dict):
                mode = config.get("provider_mode")
                if mode:
                    return mode
    except Exception:
        pass
    return "deepseek_compatible"


# ============================================================
# 检查函数
# ============================================================

def check_process_hermes() -> dict:
    """
    Check if Hermes gateway is running.
    Strategy:
      1. Try 'hermes gateway status' and parse for 'gateway is running'.
      2. Fall back to pgrep -f hermes if command is unavailable.
    """
    # Strategy 1: hermes gateway status
    try:
        result = subprocess.run(
            ["hermes", "gateway", "status"],
            capture_output=True, text=True, timeout=10,
        )
        output = result.stdout.lower()

        # 严格判断：显式排除 "not running"，避免 "running" in "not running" 假阳性
        if "gateway is running" in output:
            running = True
        elif "not running" in output:
            running = False
        elif result.returncode == 0 and "running" in output:
            running = True
        else:
            running = False

        detail_text = result.stdout.strip() if result.stdout.strip() else result.stderr.strip()
        return {
            "name": "hermes",
            "running": running,
            "method": "hermes gateway status",
            "detail": detail_text[:120],
        }
    except FileNotFoundError:
        pass  # hermes command not found, fall through
    except Exception:
        pass  # command exists but failed — try pgrep

    # Strategy 2: pgrep fallback
    try:
        result = subprocess.run(
            ["pgrep", "-f", "hermes"],
            capture_output=True, text=True, timeout=5,
        )
        running = result.returncode == 0
        pids = [p for p in result.stdout.strip().split("\n") if p]
        return {
            "name": "hermes",
            "running": running,
            "method": "pgrep",
            "detail": f"found {len(pids)} process(es)" if running else "not running",
        }
    except FileNotFoundError:
        return {"name": "hermes", "running": False, "method": "none", "detail": "pgrep not available"}
    except Exception as e:
        return {"name": "hermes", "running": False, "method": "error", "detail": f"check error: {e}"}


def check_port(port: int, host: str = "127.0.0.1", connect_timeout: float = 1.0) -> dict:
    """
    Check a single port:
      - First check ss/netstat for local listening.
      - Then attempt a TCP connect to 127.0.0.1:port.
    Returns status: listening / reachable / not available
    """
    r = {"port": port, "status": "not available", "detail": ""}

    # Step A: ss / netstat
    listening = False
    try:
        res = subprocess.run(["ss", "-tlnp"], capture_output=True, text=True, timeout=5)
        if f":{port}" in res.stdout:
            listening = True
            for line in res.stdout.split("\n"):
                if f":{port}" in line:
                    r["detail"] = line.strip()
                    break
    except FileNotFoundError:
        try:
            res = subprocess.run(["netstat", "-tlnp"], capture_output=True, text=True, timeout=5)
            if f":{port}" in res.stdout:
                listening = True
                r["detail"] = f"netstat: port {port} listening"
        except Exception:
            pass

    if listening:
        r["status"] = "listening"
        return r

    # Step B: TCP connect probe
    try:
        sock = socket_mod.socket(socket_mod.AF_INET, socket_mod.SOCK_STREAM)
        sock.settimeout(connect_timeout)
        err = sock.connect_ex((host, port))
        sock.close()
        if err == 0:
            r["status"] = "reachable"
            r["detail"] = f"TCP connect to {host}:{port} succeeded (WSL->Windows?)"
        else:
            r["detail"] = f"port {port} not available"
    except Exception as e:
        r["detail"] = f"connect error: {e}"

    return r


def check_files(paths: list[str]) -> dict:
    """Check if any of the given paths exist."""
    found = []
    for p in paths:
        if os.path.exists(p):
            found.append(p)
    return {"exists": len(found) > 0, "found": found, "checked": len(paths)}


def check_env_vars(vars_: list[str], sensitive: bool = False) -> list[dict]:
    """Check if environment variables are set.  Sensitive vars show masked output."""
    results = []
    for v in vars_:
        val = os.environ.get(v)
        if sensitive:
            results.append({
                "name": v,
                "set": val is not None,
                "display": "已设置" if val else "未设置",
            })
        else:
            results.append({
                "name": v,
                "set": val is not None,
                "display": val if val else "(not set)",
            })
    return results


def check_http_health(url: str, timeout: float = 5.0) -> dict:
    """Perform an HTTP GET health check. Returns success/status_code/time_ms."""
    start = time.monotonic()
    try:
        req = urllib.request.Request(url, method="GET")
        resp = urllib.request.urlopen(req, timeout=timeout)
        elapsed_ms = round((time.monotonic() - start) * 1000)
        return {
            "url": url,
            "success": 200 <= resp.status < 300,
            "status_code": resp.status,
            "time_ms": elapsed_ms,
            "error": None,
        }
    except Exception as e:
        elapsed_ms = round((time.monotonic() - start) * 1000)
        return {
            "url": url,
            "success": False,
            "status_code": None,
            "time_ms": elapsed_ms,
            "error": str(e),
        }


def check_feishu_http(urls: list[str], timeout: float = FEISHU_HTTP_TIMEOUT) -> list[dict]:
    """Check Feishu bot ping endpoints and return structured results.
    
    For feishu.ping:
    - If HTTP status code is received (even 400/401/403), network is reachable
    - Only true network errors (timeout, DNS, connection refused) count as fail
    """
    results = []
    for url in urls:
        start = time.monotonic()
        try:
            req = urllib.request.Request(url, method="GET")
            resp = urllib.request.urlopen(req, timeout=timeout)
            elapsed_ms = round((time.monotonic() - start) * 1000)
            # Any HTTP status code means network is reachable
            network_reachable = True
            success = 200 <= resp.status < 300
            error = None
        except urllib.error.HTTPError as e:
            # HTTP error responses still mean network is reachable
            elapsed_ms = round((time.monotonic() - start) * 1000)
            network_reachable = True
            success = False
            error = f"HTTP Error {e.code}: {e.reason}"
        except Exception as e:
            # True network errors
            elapsed_ms = round((time.monotonic() - start) * 1000)
            network_reachable = False
            success = False
            error = str(e)
        
        r = {
            "url": url,
            "success": success,
            "network_reachable": network_reachable,
            "status_code": resp.status if 'resp' in locals() else None,
            "time_ms": elapsed_ms,
            "error": error,
            "category": "feishu"
        }
        results.append(r)
    return results


def expand_env_vars(value, env_vars: dict) -> tuple[str, bool]:
    """
    Expand ${VAR_NAME} variables in string value.
    Returns (expanded_value, success)
    """
    if not isinstance(value, str):
        return str(value), True
    
    import re
    def replacer(match):
        var_name = match.group(1)
        if var_name in env_vars:
            return env_vars[var_name]
        else:
            return match.group(0)  # Keep ${VAR_NAME} if not found
    
    expanded = re.sub(r'\$\{([^}]+)\}', replacer, value)
    # Check if any ${VAR_NAME} remains unexpanded
    has_unexpanded = re.search(r'\$\{[^}]+\}', expanded)
    return expanded, not has_unexpanded


def parse_config_content(filepath: str) -> dict:
    """
    Parse an OpenClaw config file and check for required keys.
    - JSON: parse natively, check channels / bindings / channels.feishu.accounts
    - YAML: try PyYAML, check channels / bindings
    - Supports .env file parsing and ${VAR_NAME} expansion
    Returns dict with keys_found, keys_missing, parse_error, warnings.
    """
    result = {"keys_found": [], "keys_missing": [], "parse_error": None, "warnings": []}

    # Load .env file if available
    env_vars = {}
    if DOTENV_AVAILABLE:
        env_file = r"C:\Users\Administrator\.openclaw\.env"
        if os.path.exists(env_file):
            load_dotenv(env_file)
            # Get all environment variables
            env_vars = dict(os.environ)
        else:
            result["warnings"].append(".env file not found at C:\\Users\\Administrator\\.openclaw\\.env")
    else:
        result["warnings"].append("python-dotenv not available, cannot parse .env files")

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            raw = f.read()
    except Exception as e:
        result["parse_error"] = str(e)
        return result

    data = None
    # Try JSON first
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        pass

    # JSON failed, try YAML
    if data is None:
        try:
            import yaml
            data = yaml.safe_load(raw)
        except ImportError:
            result["warnings"].append(f"YAML module not available, cannot validate {filepath}")
            return result
        except Exception as e:
            result["parse_error"] = f"YAML parse error: {e}"
            return result

    if not isinstance(data, dict):
        result["parse_error"] = "top-level is not a dict"
        return result

    # Expand environment variables in the entire data structure
    def expand_recursive(obj):
        if isinstance(obj, dict):
            return {k: expand_recursive(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [expand_recursive(item) for item in obj]
        elif isinstance(obj, str):
            expanded, success = expand_env_vars(obj, env_vars)
            if not success:
                result["warnings"].append(f"Failed to expand environment variables in: {obj}")
            return expanded
        else:
            return obj
    
    data = expand_recursive(data)

    # Check required top-level keys
    for key in ["channels", "bindings"]:
        if key in data:
            result["keys_found"].append(key)
        else:
            result["keys_missing"].append(key)

    # JSON file: extra check for channels.feishu.accounts (priority), fallback to feishu.accounts
    feishu_accounts = []
    if filepath.endswith(".json"):
        feishu_found = False
        channels = data.get("channels", {})
        if isinstance(channels, dict):
            feishu = channels.get("feishu", {})
            if isinstance(feishu, dict) and "accounts" in feishu:
                result["keys_found"].append("channels.feishu.accounts")
                feishu_accounts = feishu.get("accounts") or []
                feishu_found = True
        if not feishu_found:
            feishu = data.get("feishu", {})
            if isinstance(feishu, dict) and "accounts" in feishu:
                result["keys_found"].append("feishu.accounts (top-level)")
                feishu_accounts = feishu.get("accounts") or []
                feishu_found = True
        if not feishu_found:
            result["keys_missing"].append("channels.feishu.accounts")
    else:
        # YAML or other supported formats: attempt to locate Feishu accounts via common top-level keys.
        channels = data.get("channels")
        if isinstance(channels, dict):
            feishu = channels.get("feishu", {})
            if isinstance(feishu, dict) and "accounts" in feishu:
                feishu_accounts = feishu.get("accounts") or []
        if not feishu_accounts:
            feishu = data.get("feishu", {})
            if isinstance(feishu, dict) and "accounts" in feishu:
                feishu_accounts = feishu.get("accounts") or []

    if isinstance(feishu_accounts, list):
        result["feishu_account_count"] = len(feishu_accounts)
        missing_keys = set()
        bot_identity_found = False
        unresolved_vars = []
        
        for account in feishu_accounts:
            if isinstance(account, dict):
                for key in FEISHU_REQUIRED_ACCOUNT_KEYS:
                    if key not in account:
                        missing_keys.add(key)
                    else:
                        value = account[key]
                        if isinstance(value, str) and '${' in value and '}' in value:
                            # Check if variable expansion was successful
                            expanded, success = expand_env_vars(value, env_vars)
                            if not success:
                                unresolved_vars.append(f"{key} in account")
                
                # Check app_ticket - if it's ${...} but unresolvable, it's a fail
                app_ticket = account.get("app_ticket")
                if app_ticket and isinstance(app_ticket, str) and '${' in app_ticket and '}' in app_ticket:
                    expanded, success = expand_env_vars(app_ticket, env_vars)
                    if not success:
                        unresolved_vars.append("app_ticket variable unresolvable")
                
                if any(account.get(field) for field in FEISHU_BOT_IDENTITY_FIELDS):
                    bot_identity_found = True
        
        result["feishu_missing_keys"] = sorted(missing_keys)
        result["feishu_bot_identity_status"] = "recovered" if bot_identity_found else "unknown"
        
        # Add unresolved variables as failures
        if unresolved_vars:
            result["feishu_unresolved_vars"] = unresolved_vars
        
        if result["feishu_account_count"] == 0:
            result["warnings"].append("No Feishu accounts found in OpenClaw config")
        elif result["feishu_missing_keys"]:
            result["warnings"].append(
                f"Feishu config missing keys: {', '.join(result['feishu_missing_keys'])}"
            )
        elif unresolved_vars:
            result["warnings"].append(f"Feishu config has unresolved variables: {', '.join(unresolved_vars)}")
        elif result["feishu_bot_identity_status"] == "unknown":
            result["warnings"].append("Feishu bot open_id identity is not present or not recovered")
    else:
        result["feishu_account_count"] = 0
        result["feishu_missing_keys"] = []
        result["feishu_bot_identity_status"] = "unknown"
        result["warnings"].append("Feishu account list is not a standard array in OpenClaw config")

    return result


# ============================================================
# v2.2: 失败项 / 建议动作 / MAIN 摘要
# ============================================================

def build_feishu_fail_items(config_content, feishu_http_results) -> list[dict]:
    items = []
    if feishu_http_results is not None:
        for r in feishu_http_results:
            # Only fail if network is truly unreachable (not just HTTP error responses)
            if not r.get("network_reachable", False):
                items.append({
                    "category": "feishu",
                    "name": "feishu.ping",
                    "detail": r.get("error") or "network unreachable",
                })
    if config_content is not None:
        for cr in config_content:
            fname = os.path.basename(cr.get("file", "unknown"))
            if cr.get("parse_error"):
                items.append({
                    "category": "feishu",
                    "name": "feishu.config",
                    "detail": f"{fname} parse error: {cr['parse_error']}",
                })
                continue
            if cr.get("feishu_account_count", 0) == 0:
                items.append({
                    "category": "feishu",
                    "name": "feishu.config",
                    "detail": f"{fname} has no Feishu accounts",
                })
            if cr.get("feishu_missing_keys"):
                items.append({
                    "category": "feishu",
                    "name": "feishu.config",
                    "detail": f"{fname} missing keys: {', '.join(cr['feishu_missing_keys'])}",
                })
            # Check for unresolved variables - this is a fail
            if cr.get("feishu_unresolved_vars"):
                items.append({
                    "category": "feishu",
                    "name": "feishu.config",
                    "detail": f"{fname} unresolved variables: {', '.join(cr['feishu_unresolved_vars'])}",
                })
            if cr.get("feishu_account_count", 0) > 0 and cr.get("feishu_bot_identity_status") == "unknown":
                items.append({
                    "category": "feishu",
                    "name": "feishu.bot_identity",
                    "detail": f"{fname} bot identity open_id unknown",
                })
    return items


def build_fail_items(process, cf_raw, env_required, env_sensitive, http_results, feishu_http_results=None, config_content=None, enabled_categories=None) -> list[dict]:
    """Extract failure items. Each item: {category, name, detail}."""
    items = []
    if process is not None and not process["running"]:
        items.append({"category": "process", "name": "hermes", "detail": process["detail"]})
    if cf_raw.get("checked", 0) > 0 and not cf_raw.get("exists", False):
        items.append({"category": "config", "name": "openclaw", "detail": "no config file found"})
    for r in env_required + env_sensitive:
        if not r["set"]:
            items.append({"category": "env", "name": r["name"], "detail": "未设置"})
    for r in http_results:
        if not r["success"]:
            items.append({"category": "http", "name": r["url"],
                          "detail": r.get("error") or f"status {r['status_code']}"})
    if enabled_categories is None or "feishu" in enabled_categories:
        items.extend(build_feishu_fail_items(config_content, feishu_http_results))
    return items


def build_recommended_actions(fail_items: list[dict], warnings: list[str]) -> list[str]:
    """Generate recommended actions from failures and warnings."""
    actions = []
    for fi in fail_items:
        if fi["category"] == "process":
            actions.append("Check Hermes gateway: run 'hermes gateway status' manually")
        elif fi["category"] == "config":
            actions.append("Verify OpenClaw config file exists at expected paths")
        elif fi["category"] == "env":
            actions.append(f"Set {fi['name']} in your shell profile")
        elif fi["category"] == "http":
            actions.append(f"Check service health at {fi['name']}")
        elif fi["category"] == "feishu":
            if fi["name"] == "feishu.ping":
                actions.append("Check network connectivity to open.feishu.cn and Feishu bot ping endpoint")
            elif fi["name"] == "feishu.bot_identity":
                actions.append("Wait for bot open_id recovery before accepting Feishu bot traffic")
            else:
                actions.append("Review OpenClaw Feishu account configuration and bot identity")
    actions = list(dict.fromkeys(actions))
    if warnings:
        actions.append("Review warnings for non-critical issues")
    return actions


def compute_next_action(fail_items: list[dict], warnings: list[str]) -> str:
    """none | investigate_failures | review_warnings"""
    if fail_items:
        return "investigate_failures"
    if warnings:
        return "review_warnings"
    return "none"


# ============================================================
# v2.3.1: 健康分 / 健康等级 / 故障分类 / 趋势分析 / 历史归档
# ============================================================

def compute_health_score(fail_items: list[dict]) -> int:
    """
    计算 0-100 健康分。
    - 全部通过 = 100
    - 按失败项类别扣分，HTTP 失败扣分最重
    """
    score = 100
    for fi in fail_items:
        cat = fi.get("category", "env")
        deduction = HEALTH_DEDUCTION.get(cat, 5)
        score -= deduction
    return max(0, min(100, score))


def compute_health_level(health_score: int) -> str:
    """基于 health_score 返回 green / yellow / red。"""
    if health_score >= 90:
        return "green"
    elif health_score >= 60:
        return "yellow"
    else:
        return "red"


def compute_domain_health(fail_items: list[dict], skipped_items: list[str] | None = None) -> dict:
    """Compute health score and level for a single domain. Reuses HEALTH_DEDUCTION."""
    score = 100
    for fi in fail_items:
        cat = fi.get("category", "env")
        deduction = HEALTH_DEDUCTION.get(cat, 5)
        score -= deduction
    score = max(0, min(100, score))
    if score >= 90:
        level = "green"
    elif score >= 60:
        level = "yellow"
    else:
        level = "red"
    return {"health_score": score, "health_level": level}


def classify_failures(current_fails: list[dict], previous_fails: list[dict]) -> dict:
    """
    对比当前 fail_items 与上次历史记录，分类故障：
    - new_fail_items: 本次新增
    - recovered_items: 本次恢复
    - persistent_fail_items: 持续存在

    首次运行（previous_fails 为空列表）时：
    所有 current_fails 归入 new_fail_items，其余为空数组。
    """
    # 用 (category, name) 作为唯一标识
    def _key(item: dict) -> tuple:
        return (item.get("category", ""), item.get("name", ""))

    current_keys = set(_key(fi) for fi in current_fails)
    previous_keys = set(_key(fi) for fi in previous_fails)

    new_fails = [fi for fi in current_fails if _key(fi) not in previous_keys]
    recovered = [fi for fi in previous_fails if _key(fi) not in current_keys]
    persistent = [fi for fi in current_fails if _key(fi) in previous_keys]

    return {
        "new_fail_items": new_fails,
        "recovered_items": recovered,
        "persistent_fail_items": persistent,
    }


def _load_previous_history() -> dict | None:
    """从 history/ 目录加载倒数第二份历史报告（跳过当前运行）。
    返回 dict 或 None。
    run_check_stack.sh 在 Step 3 会先 cp 当前报告到 history/，
    所以最新文件就是当前运行，我们需要倒数第二个作为"上次"对比。
    """
    if not os.path.isdir(HISTORY_DIR):
        return None
    history_files = sorted(glob.glob(os.path.join(HISTORY_DIR, "*.json")))
    # 至少需要 2 个文件才有"上一次"（最新 = 当前运行，倒数第二 = 上一次）
    if len(history_files) < 2:
        if len(history_files) == 1:
            # 只有 1 个文件 = 当前运行，没有上次数据
            return None
        return None
    # 倒数第二个 = 上一次运行
    previous_file = history_files[-2]
    try:
        with open(previous_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _load_all_history_entries(skip_count: int = 0) -> list[dict]:
    """加载 history/ 目录中所有历史记录的摘要条目。
    skip_count: 跳过最新的 N 个文件（例如 1 = 跳过当前运行）。
    """
    if not os.path.isdir(HISTORY_DIR):
        return []
    history_files = sorted(glob.glob(os.path.join(HISTORY_DIR, "*.json")))
    if skip_count > 0:
        history_files = history_files[:-skip_count] if skip_count < len(history_files) else []
    entries = []
    for hf in history_files:
        try:
            with open(hf, "r", encoding="utf-8") as f:
                data = json.load(f)
            meta = data.get("meta", {})
            summary = data.get("summary", {})
            # 尝试从 v2.3.1 报告中获取 health_score / health_level
            hs = data.get("health_score")
            hl = data.get("health_level")
            entry = {
                "run_at": meta.get("run_at", ""),
                "ok": summary.get("ok", 0),
                "fail": summary.get("fail", 0),
            }
            if hs is not None:
                entry["health_score"] = hs
            if hl is not None:
                entry["health_level"] = hl
            entries.append(entry)
        except (json.JSONDecodeError, OSError):
            continue
    return entries


def save_history(report: dict) -> None:
    """将完整报告保存到 history/ 目录，文件名格式 YYYYMMDDTHHMMSSZ.json。"""
    os.makedirs(HISTORY_DIR, exist_ok=True)
    run_at = report.get("meta", {}).get("run_at", "")
    # 将 ISO 8601 时间戳转为文件名格式: 2026-04-30T10:02:46Z → 20260430T100246Z
    ts = run_at.replace("-", "").replace(":", "").replace(" ", "T")
    if not ts.endswith("Z"):
        ts += "Z"
    filename = f"{ts}.json"
    filepath = os.path.join(HISTORY_DIR, filename)
    with open(filepath, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)
        f.write("\n")


def compute_trend(health_score: int, health_level: str, skip_count: int = 0) -> dict:
    """
    生成趋势分析结果，写入并返回 trend.json 内容。
    skip_count: 跳过最新的 N 个历史文件（1 = 跳过当前运行自身）。
    - 首次运行（无历史）: {"status": "first_run", ...}
    - 只有1条历史: {"status": "insufficient_history", "runs": [...]}
    - 2条及以上: {"status": "ok", "runs": [...], "comparison": {...}}
    """
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # 收集所有历史条目（跳过当前运行自身）
    history_entries = _load_all_history_entries(skip_count=skip_count)

    # 当前运行条目
    current_entry = {
        "run_at": now_utc,
        "ok": 0,   # 会在调用处填充
        "fail": 0,
        "health_score": health_score,
        "health_level": health_level,
    }

    if len(history_entries) == 0:
        return {
            "status": "first_run",
            "message": "No historical data available. This is the first run.",
            "runs": [current_entry],
        }

    if len(history_entries) == 1:
        prev = history_entries[-1]
        return {
            "status": "insufficient_history",
            "message": "Only one historical run found. Need at least 2 for trend comparison.",
            "runs": [prev, current_entry],
        }

    # 2+ 条历史：正常趋势
    prev = history_entries[-1]
    prev_score = prev.get("health_score")
    trend_direction = "稳定"
    if prev_score is not None:
        diff = health_score - prev_score
        if diff > 0:
            trend_direction = "改善"
        elif diff < 0:
            trend_direction = "恶化"
    else:
        # 旧版历史无 health_score，用 ok/fail 判断
        if health_score >= 90:
            trend_direction = "改善"
        elif health_score < 60:
            trend_direction = "恶化"

    comparison = {
        "previous_run_at": prev.get("run_at", ""),
        "previous_health_score": prev.get("health_score"),
        "previous_health_level": prev.get("health_level"),
        "current_health_score": health_score,
        "current_health_level": health_level,
        "trend_direction": trend_direction,
    }

    # 保留最近 50 条
    all_runs = history_entries + [current_entry]
    if len(all_runs) > 50:
        all_runs = all_runs[-50:]

    return {
        "status": "ok",
        "trend_direction": trend_direction,
        "comparison": comparison,
        "runs": all_runs,
    }


def generate_decision_hint(health_level: str, trend_direction: str, new_fails: list, persistent_fails: list) -> str:
    """生成一句话决策建议。"""
    if health_level == "green":
        if trend_direction == "改善":
            return "环境健康且持续改善，无需操作。"
        elif trend_direction == "恶化":
            return "环境仍健康但出现恶化趋势，建议关注。"
        else:
            return "环境健康，无需操作。"
    elif health_level == "yellow":
        if new_fails:
            return f"出现 {len(new_fails)} 项新故障，建议尽快排查。"
        elif persistent_fails:
            return f"存在 {len(persistent_fails)} 项持续故障，建议安排修复。"
        else:
            return "环境存在非关键问题，建议择机修复。"
    else:  # red
        if new_fails and persistent_fails:
            return f"严重：{len(new_fails)} 项新故障 + {len(persistent_fails)} 项持续故障，需立即处理。"
        elif new_fails:
            return f"严重：{len(new_fails)} 项新故障，需立即处理。"
        else:
            return f"严重：{len(persistent_fails)} 项持续故障，需立即处理。"


def compute_trend_summary(trend_result: dict) -> str:
    """将 trend status/direction 映射为 trend_summary 字符串。"""
    status = trend_result.get("status", "")
    if status == "first_run":
        return "首次运行"
    elif status == "insufficient_history":
        return "数据不足"
    else:
        return trend_result.get("trend_direction", "稳定")


# ============================================================
# MAIN 摘要（v2.3.1 扩展版）
# ============================================================

def build_main_summary(results: dict, health_info: dict | None = None) -> dict:
    """Compact MAIN-consumable JSON summary. Original 11 fields + new health/trend fields."""
    s = results["summary"]
    base = {
        "tool_name":          results["meta"]["tool_name"],
        "version":            results["meta"]["version"],
        "status":             s["status"],
        "exit_code":          s["exit_code"],
        "ok":                 s["ok"],
        "fail":               s["fail"],
        "fail_items":         results.get("fail_items", []),
        "warnings":           results.get("warnings", []),
        "checks_run":         s["checks_run"],
        "next_action":        results.get("next_action", "none"),
        "recommended_actions": results.get("recommended_actions", []),
    }
    # v2.3.1 新增字段
    if health_info:
        base["health_score"]            = health_info.get("health_score", 100)
        base["health_level"]            = health_info.get("health_level", "green")
        base["new_fail_items"]          = health_info.get("new_fail_items", [])
        base["recovered_items"]         = health_info.get("recovered_items", [])
        base["persistent_fail_items"]   = health_info.get("persistent_fail_items", [])
        base["trend_summary"]           = health_info.get("trend_summary", "首次运行")
        base["main_decision_hint"]      = health_info.get("main_decision_hint", "")
    else:
        base["health_score"]            = 100
        base["health_level"]            = "green"
        base["new_fail_items"]          = []
        base["recovered_items"]         = []
        base["persistent_fail_items"]   = []
        base["trend_summary"]           = "首次运行"
        base["main_decision_hint"]      = ""
    base["domains"] = results.get("domains", {})
    return base


def build_main_summary_text(results: dict, health_info: dict | None = None) -> str:
    """Human-readable MAIN summary text (for latest_summary.txt)."""
    ms = build_main_summary(results, health_info)
    total = ms["ok"] + ms["fail"]
    lines = [
        f"check_stack v{ms['version']} — {ms['status']}",
        f"Health: {ms['health_score']}/100 ({ms['health_level']})",
        f"Status: {ms['status']} | Exit: {ms['exit_code']}",
        f"Passed: {ms['ok']}/{total} | Failures: {ms['fail']} | Warnings: {len(ms['warnings'])}",
        f"Checks: {', '.join(ms['checks_run']) if ms['checks_run'] else '(none)'}",
    ]
    if ms["fail_items"]:
        lines.append("Fail items:")
        for fi in ms["fail_items"]:
            lines.append(f"  - [{fi['category']}] {fi['name']}: {fi['detail']}")
    if ms["new_fail_items"]:
        lines.append("New failures (since last run):")
        for fi in ms["new_fail_items"]:
            lines.append(f"  - [{fi['category']}] {fi['name']}: {fi['detail']}")
    if ms["recovered_items"]:
        lines.append("Recovered (since last run):")
        for fi in ms["recovered_items"]:
            lines.append(f"  + [{fi['category']}] {fi['name']}")
    if ms["warnings"]:
        lines.append("Warnings:")
        for w in ms["warnings"]:
            lines.append(f"  - {w}")
    lines.append(f"Trend: {ms['trend_summary']}")
    lines.append(f"Next action: {ms['next_action']}")
    lines.append(f"Decision hint: {ms['main_decision_hint']}")
    if ms["recommended_actions"]:
        lines.append("Recommended actions:")
        for a in ms["recommended_actions"]:
            lines.append(f"  - {a}")
    else:
        lines.append("Recommended actions: (none)")
    return "\n".join(lines)


# ============================================================
# 结构化结果收集
# ============================================================

def collect_results(ports: list[int], windows_user: str, verbose: bool, only_filter: str | None) -> dict:
    """
    Run checks and return a structured result dict.
    only_filter: None or "all" = run everything; else one of process|ports|config|env|http
    """
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    warnings: list[str] = []
    checks_run: list[str] = []
    run_all = only_filter in (None, "all")
    enabled_categories: set[str] = set()
    if only_filter and only_filter in CHECK_DOMAINS:
        enabled_categories = set(CHECK_DOMAINS[only_filter]["checks"])
    elif not run_all and only_filter:
        enabled_categories = {only_filter}

    config_paths = build_config_paths(windows_user)

    # ── process ──
    if run_all or "process" in enabled_categories:
        process = check_process_hermes()
        checks_run.append("process")
    else:
        process = None

    # ── ports ──
    if run_all or "ports" in enabled_categories:
        port_results = [check_port(p) for p in ports]
        checks_run.append("ports")
    else:
        port_results = []

    # ── config_files ──
    if run_all or "config" in enabled_categories or "feishu" in enabled_categories:
        cf_raw = check_files(config_paths)
        config_content = None
        if cf_raw["found"]:
            content_results = []
            for fp in cf_raw["found"]:
                cr = parse_config_content(fp)
                content_results.append({"file": fp, **cr})
                if cr.get("warnings"):
                    warnings.extend(cr["warnings"])
            config_content = content_results
        if "config" in enabled_categories:
            checks_run.append("config")
    else:
        cf_raw = {"exists": False, "found": [], "checked": 0}
        config_content = None

    # ── env_vars ──
    if run_all or "env" in enabled_categories:
        provider_mode = detect_provider_mode()
        is_anthropic = (provider_mode == "anthropic")

        if is_anthropic:
            required_vars = ["ANTHROPIC_BASE_URL", "ANTHROPIC_MODEL", "CLAUDE_CODE_SUBAGENT_MODEL"]
            sensitive_vars = ["ANTHROPIC_AUTH_TOKEN"]
            env_info_vars: list[str] = []
        else:
            required_vars: list[str] = []
            sensitive_vars: list[str] = []
            env_info_vars = ["ANTHROPIC_BASE_URL", "ANTHROPIC_MODEL", "CLAUDE_CODE_SUBAGENT_MODEL", "ANTHROPIC_AUTH_TOKEN"]

        env_required = check_env_vars(required_vars, sensitive=False)
        env_sensitive = check_env_vars(sensitive_vars, sensitive=True)
        env_info = check_env_vars(env_info_vars, sensitive=True) if env_info_vars else []
        checks_run.append("env")
    else:
        env_required = []
        env_sensitive = []
        env_info = []

    # ── http_checks ──
    if run_all or "http" in enabled_categories:
        http_results = [check_http_health(u) for u in HTTP_HEALTH_URLS]
        checks_run.append("http")
    else:
        http_results = []

    # ── feishu_checks ──
    feishu_http_results = None
    if run_all or "feishu" in enabled_categories:
        feishu_http_results = check_feishu_http(FEISHU_HEALTH_URLS)
        checks_run.append("feishu")
    
    # ── summary ──
    ok = 0
    fail = 0

    if process is not None:
        if process["running"]:
            ok += 1
        else:
            fail += 1

    for r in port_results:
        if r["status"] in ("listening", "reachable"):
            ok += 1

    if cf_raw["exists"]:
        ok += 1
    elif cf_raw["checked"] > 0:
        fail += 1

    for r in env_required + env_sensitive:
        if r["set"]:
            ok += 1
        else:
            fail += 1

    for r in http_results:
        if r["success"]:
            ok += 1
        else:
            fail += 1

    if feishu_http_results is not None:
        for r in feishu_http_results:
            if r["success"]:
                ok += 1
            else:
                fail += 1

    if config_content is not None:
        has_valid_feishu = any(
            cr.get("feishu_account_count", 0) > 0 and not cr.get("feishu_missing_keys")
            for cr in config_content
        )
        if has_valid_feishu:
            ok += 1
        else:
            fail += 1

    total = ok + fail
    fail_items = build_fail_items(
        process, cf_raw, env_required, env_sensitive, http_results,
        feishu_http_results=feishu_http_results,
        config_content=config_content,
        enabled_categories=enabled_categories if not run_all else None,
    )
    recommended_actions = build_recommended_actions(fail_items, warnings)
    next_action = compute_next_action(fail_items, warnings)

    # ── v2.4.0: 检查域分层 ──
    # Separate fail_items by domain
    mainline_categories = set(CHECK_DOMAINS["mainline"]["checks"])
    channel_infra_categories = set(CHECK_DOMAINS["channel_infra"]["checks"])

    mainline_fail_items = [fi for fi in fail_items if fi["category"] in mainline_categories]
    channel_infra_fail_items = [fi for fi in fail_items if fi["category"] in channel_infra_categories]
    special_branch_fail_items = [
        fi for fi in fail_items
        if fi["category"] not in mainline_categories and fi["category"] not in channel_infra_categories
    ]

    # Per-domain checks data
    mainline_domain_checks: dict = {}
    if process is not None:
        mainline_domain_checks["process"] = process
    if port_results:
        mainline_domain_checks["ports"] = port_results
    mainline_domain_checks["config"] = {
        "exists": cf_raw["exists"],
        "checked_count": cf_raw["checked"],
        "found": cf_raw["found"],
    }
    if env_required or env_sensitive:
        mainline_domain_checks["env"] = {"required": env_required, "sensitive": env_sensitive}
    if http_results:
        mainline_domain_checks["http"] = http_results

    channel_infra_domain_checks: dict = {}
    if feishu_http_results is not None:
        channel_infra_domain_checks["feishu"] = feishu_http_results
    if config_content is not None:
        channel_infra_domain_checks["feishu_config"] = config_content

    # Track skipped items per domain
    mainline_skipped: list[str] = []
    channel_infra_skipped: list[str] = []
    special_branch_skipped: list[str] = []
    if not run_all:
        for check_name in CHECK_DOMAINS["mainline"]["checks"]:
            if check_name not in checks_run:
                mainline_skipped.append(check_name)
        for check_name in CHECK_DOMAINS["channel_infra"]["checks"]:
            if check_name not in checks_run:
                channel_infra_skipped.append(check_name)
        for check_name in CHECK_DOMAINS["special_branch"]["checks"]:
            if check_name not in checks_run:
                special_branch_skipped.append(check_name)

    # Compute per-domain health
    mainline_health = compute_domain_health(mainline_fail_items)
    channel_infra_health = compute_domain_health(channel_infra_fail_items)
    special_branch_health = compute_domain_health(special_branch_fail_items)

    # Build domains structure
    domains = {
        "mainline": {
            "health_score": mainline_health["health_score"],
            "health_level": mainline_health["health_level"],
            "checks": mainline_domain_checks,
            "fail_items": mainline_fail_items,
            "skipped_items": mainline_skipped,
        },
        "channel_infra": {
            "health_score": channel_infra_health["health_score"],
            "health_level": channel_infra_health["health_level"],
            "checks": channel_infra_domain_checks,
            "fail_items": channel_infra_fail_items,
            "skipped_items": channel_infra_skipped,
        },
        "special_branch": {
            "health_score": special_branch_health["health_score"],
            "health_level": special_branch_health["health_level"],
            "checks": {},
            "fail_items": special_branch_fail_items,
            "skipped_items": special_branch_skipped,
        },
    }

    # ── v2.3.1: health_score / health_level (top-level from mainline only) ──
    health_score = mainline_health["health_score"]
    health_level = mainline_health["health_level"]

    # ── v2.3.1: 故障分类（对比历史） ──
    previous_report = _load_previous_history()
    previous_fails = previous_report.get("fail_items", []) if previous_report else []
    classification = classify_failures(fail_items, previous_fails)

    # ── v2.3.1: 趋势分析 ──
    # 当从 run_check_stack.sh 调用时，history/ 已包含当前运行，
    # 所以 skip_count=1 跳过当前运行自身
    trend_result = compute_trend(health_score, health_level, skip_count=1)
    # 填充 ok/fail 到当前 entry
    if "runs" in trend_result and trend_result["runs"]:
        current_entry = trend_result["runs"][-1]
        current_entry["ok"] = ok
        current_entry["fail"] = fail

    trend_summary = compute_trend_summary(trend_result)
    trend_direction = trend_result.get("trend_direction", "稳定")

    # ── v2.3.1: 决策建议 ──
    main_decision_hint = generate_decision_hint(
        health_level, trend_direction,
        classification["new_fail_items"],
        classification["persistent_fail_items"],
    )

    # 组装 health_info（传递给 build_main_summary）
    health_info = {
        "health_score": health_score,
        "health_level": health_level,
        "new_fail_items": classification["new_fail_items"],
        "recovered_items": classification["recovered_items"],
        "persistent_fail_items": classification["persistent_fail_items"],
        "trend_summary": trend_summary,
        "main_decision_hint": main_decision_hint,
    }

    return {
        "meta": {
            "tool_name": "check_stack",
            "version": VERSION,
            "run_at": now_utc,
            "hostname": socket_mod.gethostname(),
            "platform": platform.system(),
            "windows_user": windows_user,
            "cwd": os.getcwd(),
        },
        "process": process,
        "ports": port_results,
        "config_files": {
            "openclaw": {
                "exists": cf_raw["exists"],
                "checked_count": cf_raw["checked"],
                "found": cf_raw["found"],
                "content": config_content,
            },
        },
        "env_vars": {
            "required": env_required,
            "sensitive": env_sensitive,
            "info": env_info,
        },
        "http_checks": http_results,
        "feishu_checks": feishu_http_results if feishu_http_results is not None else [],
        "fail_items": fail_items,
        "recommended_actions": recommended_actions,
        "next_action": next_action,
        "warnings": warnings,
        "summary": {
            "ok": ok,
            "fail": fail,
            "total": total,
            "status": "ALL_OK" if fail == 0 else "HAS_FAILURES",
            "exit_code": 0 if fail == 0 else 1,
            "checks_run": checks_run,
        },
        # v2.3.1 新增顶层字段
        "health_score": health_score,
        "health_level": health_level,
        "health_info": health_info,
        "domains": domains,
    }


# ============================================================
# 输出函数
# ============================================================

def _show_process(p: dict) -> None:
    if p is None:
        return
    print("\n── 1. 进程检查 ──")
    if p["running"]:
        print(f"  [OK] hermes 运行中  (method: {p['method']})")
        print(f"        {p['detail']}")
    else:
        print(f"  [FAIL] hermes: {p['detail']}  (method: {p['method']})")


def _show_ports(ports: list[dict]) -> None:
    if not ports:
        return
    print(f"\n── 2. 端口检查 (共 {len(ports)} 个) ──")
    for r in ports:
        if r["status"] == "listening":
            print(f"  [OK] port {r['port']:>5}  listening  {r['detail']}")
        elif r["status"] == "reachable":
            print(f"  [OK] port {r['port']:>5}  reachable  {r['detail']}")
        else:
            print(f"  [--] port {r['port']:>5}  not available")


def _show_config(cf: dict) -> None:
    if cf["checked_count"] == 0:
        return
    print(f"\n── 3. 配置文件检查 (OpenClaw, 已搜索 {cf['checked_count']} 个路径) ──")
    if cf["exists"]:
        for p in cf["found"]:
            print(f"  [OK] {p}")
        # Content validation
        content = cf.get("content")
        if content:
            for cr in content:
                fname = os.path.basename(cr["file"])
                if cr["parse_error"]:
                    print(f"  [--] {fname}: parse error — {cr['parse_error']}")
                else:
                    if cr["keys_found"]:
                        print(f"       {fname} keys found: {', '.join(cr['keys_found'])}")
                    if cr["keys_missing"]:
                        print(f"       {fname} keys missing: {', '.join(cr['keys_missing'])}")
    else:
        print(f"  [FAIL] 未找到 OpenClaw 配置文件")


def _show_env(env_required: list[dict], env_sensitive: list[dict], env_info: list[dict] | None = None) -> None:
    if not env_required and not env_sensitive and not (env_info or []):
        return
    print("\n── 4. 环境变量检查 ──")
    for r in env_required:
        if r["set"]:
            print(f"  [OK] {r['name']} = {r['display']}")
        else:
            print(f"  [FAIL] {r['name']} 未设置")
    for r in env_sensitive:
        if r["set"]:
            print(f"  [OK] {r['name']}: {r['display']}")
        else:
            print(f"  [FAIL] {r['name']}: {r['display']}")
    if env_info:
        for r in env_info:
            if r["set"]:
                print(f"  [INFO] {r['name']}: {r['display']}")
            else:
                print(f"  [INFO] {r['name']}: 未设置 (非当前 provider 所需)")


def _show_http(http_results: list[dict]) -> None:
    if not http_results:
        return
    print(f"\n── 5. HTTP 健康检查 (共 {len(http_results)} 个) ──")
    for r in http_results:
        if r["success"]:
            print(f"  [OK] {r['url']} → {r['status_code']} ({r['time_ms']}ms)")
        else:
            err = r.get("error") or f"status {r['status_code']}"
            print(f"  [FAIL] {r['url']} → {err} ({r['time_ms']}ms)")


def _show_feishu(feishu_checks: list[dict], config_content: list[dict] | None) -> None:
    if not feishu_checks and not config_content:
        return
    print(f"\n── 6. Feishu 诊断 (OpenClaw bot identity / ping) ──")
    if feishu_checks:
        for r in feishu_checks:
            if r["success"]:
                print(f"  [OK] {r['url']} → {r['status_code']} ({r['time_ms']}ms)")
            else:
                err = r.get("error") or f"status {r['status_code']}"
                print(f"  [FAIL] {r['url']} → {err} ({r['time_ms']}ms)")
    if config_content:
        for cr in config_content:
            fname = os.path.basename(cr.get("file", "unknown"))
            if cr.get("parse_error"):
                print(f"  [FAIL] {fname}: parse error — {cr['parse_error']}")
                continue
            print(f"  [OK] {fname} Feishu account count: {cr.get('feishu_account_count', 0)}")
            if cr.get("feishu_missing_keys"):
                print(f"       missing keys: {', '.join(cr['feishu_missing_keys'])}")
            print(f"       bot identity: {cr.get('feishu_bot_identity_status', 'unknown')}")


def _show_warnings(warnings: list[str]) -> None:
    if not warnings:
        return
    print(f"\n── warnings ({len(warnings)} 条) ──")
    for w in warnings:
        print(f"  [!] {w}")


def print_text_report(results: dict, verbose: bool) -> None:
    """Print human-readable report."""
    print("=" * 56)
    print("  Environment Stack Check")
    print("=" * 56)

    _show_process(results["process"])
    _show_ports(results["ports"])
    _show_config(results["config_files"]["openclaw"])
    _show_env(results["env_vars"]["required"], results["env_vars"]["sensitive"], results["env_vars"].get("info", []))
    _show_http(results["http_checks"])
    _show_feishu(results.get("feishu_checks", []), results["config_files"]["openclaw"]["content"])
    _show_warnings(results.get("warnings", []))

    if verbose:
        print(f"\n── verbose ──")
        print(f"  checks_run: {results['summary'].get('checks_run', [])}")
        print(f"  ports checked: {[r['port'] for r in results['ports']]}")

    s = results["summary"]
    hs = results.get("health_score", 100)
    hl = results.get("health_level", "green")
    print("\n" + "=" * 56)
    print(f"  最终总结: {s['ok']}/{s['total']} 项通过")
    print(f"  健康分: {hs}/100 ({hl})")
    if s["status"] == "ALL_OK":
        print("  状态: ALL OK")
    else:
        print(f"  状态: {s['fail']} 项未通过")
    print("=" * 56)


# ============================================================
# 主流程
# ============================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Environment stack check")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of text")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--windows-user", default=DEFAULT_WINDOWS_USER,
                        help=f"Windows username for WSL path mapping (default: {DEFAULT_WINDOWS_USER})")
    parser.add_argument("--ports", default=None,
                        help="Comma-separated port list (e.g. 18642,18648,8644)")
    parser.add_argument("--only", default=None,
                        choices=["process", "ports", "config", "env", "http", "feishu", "all",
                             "mainline", "channel_infra", "special_branch"],
                        help="Run only specified check category")
    parser.add_argument("--output", default=None,
                        help="Write output to file (for --json / --summary-json / --summary-text)")
    parser.add_argument("--summary-json", action="store_true",
                        help="Output compact MAIN-consumable summary JSON")
    parser.add_argument("--summary-text", action="store_true",
                        help="Output human-readable MAIN summary text")
    parser.add_argument("--update-trend", action="store_true",
                        help="Read latest_report.json + history/ and update trend.json (called by run_check_stack.sh)")
    return parser.parse_args()


def main():
    try:
        args = parse_args()
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 2

    # ── v2.3.1: --update-trend 模式（由 run_check_stack.sh 调用） ──
    if getattr(args, "update_trend", False):
        try:
            # 读取 latest_report.json
            latest_path = os.path.join(REPORTS_DIR, "latest_report.json")
            with open(latest_path, "r", encoding="utf-8") as f:
                latest_report = json.load(f)
            hs = latest_report.get("health_score", 100)
            hl = latest_report.get("health_level", "green")
            ok = latest_report.get("summary", {}).get("ok", 0)
            fail = latest_report.get("summary", {}).get("fail", 0)
            run_at = latest_report.get("meta", {}).get("run_at", "")

            # 计算趋势（skip_count=1 跳过当前运行自身）
            trend_result = compute_trend(hs, hl, skip_count=1)
            # 用实际 run_at 替换 now_utc 生成的当前条目
            if "runs" in trend_result and trend_result["runs"]:
                current_entry = trend_result["runs"][-1]
                current_entry["run_at"] = run_at
                current_entry["ok"] = ok
                current_entry["fail"] = fail
            os.makedirs(REPORTS_DIR, exist_ok=True)
            trend_path = os.path.join(REPORTS_DIR, "trend.json")
            with open(trend_path, "w") as f:
                json.dump(trend_result, f, indent=2, ensure_ascii=False, default=str)
                f.write("\n")
            return 0
        except Exception as e:
            print(f"ERROR: failed to update trend: {e}", file=sys.stderr)
            return 2

    try:
        # Resolve ports
        if args.ports:
            ports = [int(p.strip()) for p in args.ports.split(",") if p.strip()]
        else:
            ports = DEFAULT_PORTS

        results = collect_results(ports, args.windows_user, args.verbose, args.only)
        health_info = results.get("health_info", {})

        use_json = args.json or args.output is not None or args.summary_json or args.summary_text

        if use_json:
            # Ensure sensitive values are never in JSON
            for r in results["env_vars"]["sensitive"]:
                r.pop("value", None)

            if args.summary_json:
                out = build_main_summary(results, health_info)
                json_text = json.dumps(out, indent=2, ensure_ascii=False, default=str)
                if args.output:
                    with open(args.output, "w") as f:
                        f.write(json_text + "\n")
                else:
                    print(json_text)
            elif args.summary_text:
                text = build_main_summary_text(results, health_info)
                if args.output:
                    with open(args.output, "w") as f:
                        f.write(text + "\n")
                else:
                    print(text)
            else:
                json_text = json.dumps(results, indent=2, ensure_ascii=False, default=str)
                if args.output:
                    with open(args.output, "w") as f:
                        f.write(json_text + "\n")
                    if not args.json:
                        print(f"JSON written to {args.output}")
                else:
                    print(json_text)
        else:
            print_text_report(results, args.verbose)

        return results["summary"]["exit_code"]

    except Exception as e:
        err_result = {
            "meta": {
                "tool_name": "check_stack",
                "version": VERSION,
                "run_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "hostname": socket_mod.gethostname(),
                "platform": platform.system(),
                "windows_user": args.windows_user if "args" in dir() else "unknown",
                "cwd": os.getcwd(),
            },
            "process": None,
            "ports": None,
            "config_files": None,
            "env_vars": None,
            "http_checks": None,
            "fail_items": [],
            "recommended_actions": [],
            "next_action": "none",
            "warnings": [],
            "summary": {
                "ok": 0,
                "fail": 1,
                "total": 1,
                "status": "SCRIPT_ERROR",
                "exit_code": 2,
                "checks_run": [],
            },
            "error": str(e),
        }
        if "args" in dir() and (getattr(args, "json", False) or getattr(args, "output", None)
                                or getattr(args, "summary_json", False)
                                or getattr(args, "summary_text", False)):
            print(json.dumps(err_result, indent=2, ensure_ascii=False, default=str))
        else:
            print(f"FATAL: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
