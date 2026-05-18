#!/bin/bash
# 可视化治理仪表盘 — 启动脚本
VENV=/home/cy/hermes-agent/venv
PORT=${1:-18651}
exec $VENV/bin/uvicorn app:app --host 0.0.0.0 --port $PORT --reload
