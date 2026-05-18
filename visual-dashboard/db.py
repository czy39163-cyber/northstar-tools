"""
数据库查询层 — 可视化治理仪表盘数据源

从 PostgreSQL (CY_Database) 读取治理数据：
- task_ledger 任务状态统计
- task_execution_event 事件概览
- agent 进程/端口检查
"""

import os
import subprocess
from datetime import datetime, timedelta
from typing import Optional

import pg8000

DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 5432,
    "database": "CY_Database",
    "user": "hermes_writer",
    "password": "MAIN2025",
}

REPORT_DIR = os.path.expanduser("~/.hermes/profiles/main/reports/agent_status_daily")
SCRIPTS_DIR = os.path.expanduser("~/.hermes/profiles/main/scripts")
PROFILES_DIR = os.path.expanduser("~/.hermes/profiles")


def get_conn():
    return pg8000.connect(**DB_CONFIG)


# ─── Agent 定义 ─────────────────────────────────────────

AGENTS = [
    {"name": "MAIN", "display": "大龙虾", "emoji": "🦞", "port": 18642, "profile": "main", "domain": "main"},
    {"name": "OPS", "display": "九节虾", "emoji": "🦐", "port": 18646, "profile": "ops", "domain": "ops"},
    {"name": "DSG", "display": "皮皮虾", "emoji": "🦐", "port": 18645, "profile": "dsg", "domain": "dsg"},
    {"name": "SALES", "display": "基围虾", "emoji": "🦐", "port": 18647, "profile": "sales", "domain": "sal"},
    {"name": "FIN", "display": "黄金虾", "emoji": "📈", "port": 18649, "profile": "fin", "domain": "fin"},
    {"name": "learner", "display": "青草虾", "emoji": "🦐", "port": 18644, "profile": "learner", "domain": "main"},
    {"name": "BLD", "display": "铁甲虾", "emoji": "🔨", "port": None, "profile": None, "domain": None, "resident": False},
]


# ─── Agent 健康检查 ─────────────────────────────────────

def check_port_listening(port: Optional[int]) -> bool:
    """检查端口是否在监听"""
    if port is None:
        return False
    try:
        result = subprocess.run(["ss", "-tlnp"], capture_output=True, text=True, timeout=5)
        return f":{port}" in result.stdout
    except Exception:
        return False


def check_process(profile_name: Optional[str]):
    """检查 gateway 进程"""
    if profile_name is None:
        return False, "N/A"
    try:
        result = subprocess.run(["ps", "aux"], capture_output=True, text=True, timeout=5)
        for line in result.stdout.splitlines():
            if profile_name in line and "hermes" in line and "grep" not in line:
                parts = line.split()
                if parts:
                    return True, parts[1]
        return False, "N/A"
    except Exception:
        return False, "N/A"


def check_errors_log(profile_name: Optional[str], hours=24):
    """检查 errors.log 最近 N 小时错误数"""
    if profile_name is None:
        return False, 0
    log_path = os.path.join(PROFILES_DIR, profile_name, "errors.log")
    if not os.path.exists(log_path):
        return False, 0
    try:
        cutoff = datetime.now() - timedelta(hours=hours)
        cutoff_str = cutoff.strftime("%Y-%m-%d %H:%M")
        count = 0
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if cutoff_str in line:
                    count += 1
        return count > 0, count
    except Exception:
        return False, 0


# ─── DB 查询 ────────────────────────────────────────────

def query_task_stats():
    """任务状态统计"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT current_status, COUNT(*) as c
        FROM task_ledger
        GROUP BY current_status
        ORDER BY c DESC
    """)
    stats = [{"status": row[0], "count": row[1]} for row in cur.fetchall()]

    # 今日任务
    today = datetime.now().strftime("%Y-%m-%d")
    cur.execute("""
        SELECT COUNT(*) FROM task_ledger
        WHERE created_at::date = %s
    """, (today,))
    today_count = cur.fetchone()[0]

    # 本周任务
    week_start = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    cur.execute("""
        SELECT COUNT(*) FROM task_ledger
        WHERE created_at::date >= %s
    """, (week_start,))
    week_count = cur.fetchone()[0]

    conn.close()
    return {
        "stats": stats,
        "today": today_count,
        "week": week_count,
        "total": sum(s["count"] for s in stats),
    }


def query_agent_health():
    """全 agent 健康检测"""
    results = []
    for agent in AGENTS:
        is_resident = agent.get("resident", True)
        online, pid = check_process(agent["profile"])
        port_ok = check_port_listening(agent.get("port"))
        has_errors, error_count = check_errors_log(agent["profile"])

        if not is_resident:
            status = "非常驻"
            status_class = "non-resident"
        elif online and port_ok:
            status = "在线"
            status_class = "online"
        elif online:
            status = "进程在但端口异常"
            status_class = "warning"
        else:
            status = "离线"
            status_class = "offline"

        results.append({
            "name": agent["name"],
            "display": agent["display"],
            "emoji": agent["emoji"],
            "port": agent["port"],
            "pid": pid,
            "online": online,
            "port_ok": port_ok,
            "status": status,
            "status_class": status_class,
            "has_errors": has_errors,
            "error_count": error_count,
        })
    return results


def query_recent_tasks(limit=10):
    """最新任务"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT task_id, title, current_status, domain, assigned_to, created_at, updated_at
        FROM task_ledger
        ORDER BY updated_at DESC LIMIT %s
    """, (limit,))
    cols = [d[0] for d in cur.description]
    tasks = [dict(zip(cols, row)) for row in cur.fetchall()]
    conn.close()
    return tasks


def query_failed_blocked():
    """异常任务（failed/blocked 超24h）"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT task_id, title, current_status, assigned_to, updated_at, last_error_message
        FROM task_ledger
        WHERE current_status IN ('failed', 'blocked')
          AND updated_at < NOW() - INTERVAL '24 hours'
        ORDER BY updated_at ASC
    """)
    cols = [d[0] for d in cur.description]
    tasks = []
    for row in cur.fetchall():
        t = dict(zip(cols, row))
        if t.get("last_error_message"):
            t["last_error_message"] = str(t["last_error_message"])[:120]
        tasks.append(t)
    conn.close()
    return tasks


def query_domain_stats():
    """按 domain 统计任务"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT domain, current_status, COUNT(*) as c
        FROM task_ledger
        WHERE domain IS NOT NULL
        GROUP BY domain, current_status
        ORDER BY domain, c DESC
    """)
    data = {}
    for row in cur.fetchall():
        dom, status, cnt = row[0], row[1], row[2]
        if dom not in data:
            data[dom] = {"domain": dom, "total": 0, "statuses": {}}
        data[dom]["total"] += cnt
        data[dom]["statuses"][status] = cnt
    conn.close()
    return list(data.values())


def query_event_stats(last_hours=24):
    """最近事件统计"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT event_type, COUNT(*) as c
        FROM task_execution_event
        WHERE event_time >= NOW() - INTERVAL '%s hours'
        GROUP BY event_type
        ORDER BY c DESC
    """, (int(last_hours),))
    events = [{"type": row[0], "count": row[1]} for row in cur.fetchall()]

    cur.execute("""
        SELECT COUNT(*) FROM task_execution_event
        WHERE event_time >= NOW() - INTERVAL '%s hours'
    """, (int(last_hours),))
    total = cur.fetchone()[0]
    conn.close()
    return {"events": events, "total": total}


def query_running_tasks():
    """进行中的任务"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT task_id, title, current_status, assigned_to, created_at, updated_at
        FROM task_ledger
        WHERE current_status IN ('in_progress', 'pending', 'running', 'queued')
        ORDER BY updated_at DESC LIMIT 20
    """)
    cols = [d[0] for d in cur.description]
    tasks = [dict(zip(cols, row)) for row in cur.fetchall()]
    conn.close()
    return tasks


def load_last_report():
    """读取最近一次 agent_status_daily 报告"""
    report_path = os.path.join(REPORT_DIR)
    if not os.path.isdir(report_path):
        return None
    reports = [f for f in os.listdir(report_path) if f.endswith(".json")]
    if not reports:
        return None
    latest = sorted(reports)[-1]
    import json
    with open(os.path.join(report_path, latest), "r") as f:
        return json.load(f)
