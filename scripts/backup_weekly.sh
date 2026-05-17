#!/bin/bash
# 龙虾系统每周备份 — 数据 + 配置 dump
# Cron: 0 3 * * 0  (每周日凌晨 3:00)
set -euo pipefail

BACKUP_DIR="/mnt/f/龙虾系统/Seafile/龙虾备份"
mkdir -p "$BACKUP_DIR"
DATE=$(date +%Y%m%d)
LOG="$BACKUP_DIR/backup_$DATE.log"
exec > >(tee -a "$LOG") 2>&1

echo "=== 龙虾系统备份 $DATE ==="

# --- PostgreSQL task_ledger ---
echo "[1/4] PostgreSQL dump..."
pg_dump -h localhost -U hermes_writer CY_Database > "$BACKUP_DIR/task_ledger_$DATE.sql" 2>&1 && \
    echo "  OK: task_ledger_$DATE.sql" || echo "  FAILED"

# --- GPG encrypted config bundle ---
echo "[2/4] Config bundle..."
CONFIG_TAR="$BACKUP_DIR/configs_$DATE.tar"
tar cf "$CONFIG_TAR" \
    -C "$HOME" \
    .hermes/profiles/main/.env \
    .hermes/profiles/main/config.yaml \
    .hermes/profiles/main/SOUL.md \
    .hermes/profiles/dsg/.env \
    .hermes/profiles/dsg/config.yaml \
    .hermes/profiles/dsg/SOUL.md \
    .hermes/profiles/ops/.env \
    .hermes/profiles/ops/config.yaml \
    .hermes/profiles/ops/SOUL.md \
    .hermes/profiles/sales/.env \
    .hermes/profiles/sales/config.yaml \
    .hermes/profiles/sales/SOUL.md \
    .hermes/profiles/fin/.env \
    .hermes/profiles/fin/config.yaml \
    .hermes/profiles/fin/SOUL.md \
    .hermes/profiles/learner/config.yaml \
    .hermes/profiles/learner/SOUL.md \
    .hermes/profiles/strategist/config.yaml \
    .hermes/profiles/strategist/SOUL.md \
    .hermes/.env \
    2>/dev/null

# Encrypt with GPG (key: czy39163@gmail.com)
gpg --encrypt --recipient czy39163@gmail.com \
    --output "$CONFIG_TAR.gpg" "$CONFIG_TAR" 2>&1 && \
    rm "$CONFIG_TAR" && \
    echo "  OK: configs_$DATE.tar.gpg" || echo "  FAILED"

# --- Hermes custom files ---
echo "[3/4] Hermes patches..."
PATCH_DIR="$BACKUP_DIR/hermes_patches_$DATE"
mkdir -p "$PATCH_DIR"
cp /home/cy/hermes-agent/gateway/platforms/feishu.py "$PATCH_DIR/"
cp /home/cy/hermes-agent/gateway/platforms/weixin.py "$PATCH_DIR/"
cp /home/cy/.hermes/scripts/gpt-loop.sh "$PATCH_DIR/"
echo "  OK: $PATCH_DIR"

# --- Cleanup old backups (keep 12 weeks) ---
echo "[4/4] Cleanup..."
find "$BACKUP_DIR" -name "*.sql" -mtime +84 -delete 2>/dev/null || true
find "$BACKUP_DIR" -name "*.gpg" -mtime +84 -delete 2>/dev/null || true
echo "  OK"

echo "=== 备份完成 ==="