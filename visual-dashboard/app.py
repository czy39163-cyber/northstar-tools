"""
可视化治理仪表盘 — FastAPI 应用

治理总览面板：
- Agent 健康状态
- 任务统计
- 异常任务
- 最近任务列表
- 今日/本周活动概览

服务端口: 18651 (可配置)
运行: uvicorn app:app --host 0.0.0.0 --port 18651
"""

import json
import os
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from db import (
    load_last_report,
    query_agent_health,
    query_domain_stats,
    query_event_stats,
    query_failed_blocked,
    query_recent_tasks,
    query_running_tasks,
    query_task_stats,
)

app = FastAPI(title="可视化治理仪表盘")

# 模板和静态文件
TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def fmt_time(val):
    """格式化时间显示"""
    if val is None:
        return "N/A"
    if isinstance(val, str):
        try:
            val = datetime.fromisoformat(val.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return val[:16]
    try:
        return val.strftime("%m-%d %H:%M")
    except Exception:
        return str(val)[:16]


def time_ago(val):
    """计算距现在的时间描述"""
    if val is None:
        return "N/A"
    try:
        if isinstance(val, str):
            val = datetime.fromisoformat(val.replace("Z", "+00:00"))
        now = datetime.now(val.tzinfo) if val.tzinfo else datetime.now()
        ref = val if val.tzinfo else val.replace(tzinfo=None)
        delta = now - ref
        days = delta.days
        hours = delta.seconds // 3600
        if days >= 7:
            return f"{days}天前"
        elif days >= 1:
            return f"{days}天{hours}小时前"
        elif hours >= 1:
            return f"{hours}小时前"
        else:
            return "刚刚"
    except Exception:
        return fmt_time(val)


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """主仪表盘页面"""
    try:
        task_stats = query_task_stats()
    except Exception as e:
        task_stats = {"error": str(e), "stats": [], "today": 0, "week": 0, "total": 0}

    try:
        agent_health = query_agent_health()
    except Exception as e:
        agent_health = {"error": str(e)}

    try:
        recent_tasks = query_recent_tasks(15)
    except Exception as e:
        recent_tasks = {"error": str(e)}

    try:
        failed_blocked = query_failed_blocked()
    except Exception as e:
        failed_blocked = {"error": str(e)}

    try:
        running_tasks = query_running_tasks()
    except Exception as e:
        running_tasks = {"error": str(e)}

    try:
        domain_stats = query_domain_stats()
    except Exception as e:
        domain_stats = {"error": str(e)}

    try:
        event_stats = query_event_stats(24)
    except Exception as e:
        event_stats = {"error": str(e)}

    try:
        last_report = load_last_report()
    except Exception:
        last_report = None

    now = datetime.now()

    return templates.TemplateResponse("index.html", {
        "request": request,
        "now": now,
        "task_stats": task_stats,
        "agent_health": agent_health,
        "recent_tasks": recent_tasks,
        "failed_blocked": failed_blocked,
        "running_tasks": running_tasks,
        "domain_stats": domain_stats,
        "event_stats": event_stats,
        "last_report": last_report,
        "fmt_time": fmt_time,
        "time_ago": time_ago,
    })


@app.get("/api/health")
async def api_health():
    """API 健康检查端点"""
    return {"status": "ok", "time": datetime.now().isoformat()}


@app.get("/api/agents")
async def api_agents():
    """Agent 健康状态 API"""
    try:
        agents = query_agent_health()
        return {"agents": agents}
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/tasks")
async def api_tasks():
    """任务统计 API"""
    try:
        stats = query_task_stats()
        return stats
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/failed")
async def api_failed():
    """异常任务 API"""
    try:
        tasks = query_failed_blocked()
        return {"tasks": tasks}
    except Exception as e:
        return {"error": str(e)}
