#!/usr/bin/env bash
# ─────────────────────────────────────────────────
# run_observation_cycle.sh
# 北极星计划阶段1 — 观察期统一包装脚本
# 由 cron 调用，不推送飞书，不修改 task_ledger
# ─────────────────────────────────────────────────
set -euo pipefail

BASEDIR="$(cd "$(dirname "$0")" && pwd)"
REPORTS_DIR="${BASEDIR}/reports/check_stack"
CS_HISTORY_DIR="${REPORTS_DIR}/history"
OBS_DIR="${REPORTS_DIR}/observation"
OBS_HISTORY_DIR="${OBS_DIR}/history"
TS_UTC="$(date -u +%Y%m%dT%H%M%SZ)"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
RUN_ID="${TIMESTAMP}"

# ── 确保目录存在 ──
mkdir -p "${CS_HISTORY_DIR}" "${OBS_HISTORY_DIR}"

LOG_FILE="${OBS_DIR}/cycle_${RUN_ID}.log"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "${LOG_FILE}"; }
log "════════════════════════════════════════"
log "观察期巡检开始 run_id=${RUN_ID}"

# ── Step 1: check_stack.py（复用 run_check_stack.sh 的完整写入流程） ──
log "[Step 1/3] 执行 check_stack.py (full report pipeline) ..."

# 临时关闭 errexit：check_stack exit=1 表示"有失败项"（正常业务），不是 fatal
set +e

# 1a: 生成带时间戳的完整 JSON 报告
python3 "${BASEDIR}/check_stack.py" --json --output "${REPORTS_DIR}/${TS_UTC}.json" >> "${LOG_FILE}" 2>&1
CS_EXIT=$?
if [ "${CS_EXIT}" -eq 2 ]; then
    log "[Step 1/3] check_stack.py FATAL exit, aborting"
    set -e
    exit 2
fi

# 1b: 更新 latest_report.json + 归档 history/
cp "${REPORTS_DIR}/${TS_UTC}.json" "${REPORTS_DIR}/latest_report.json"
if [ $? -ne 0 ]; then
    log "[Step 1/3] FATAL: failed to update latest_report.json"
    set -e
    exit 2
fi
cp "${REPORTS_DIR}/${TS_UTC}.json" "${CS_HISTORY_DIR}/${TS_UTC}.json" || {
    log "[Step 1/3] WARNING: failed to archive to history/"
}

# 1c: 生成 latest_main_summary.json（observation 读取的数据源）
python3 "${BASEDIR}/check_stack.py" --summary-json > "${REPORTS_DIR}/latest_main_summary.json" 2>>"${LOG_FILE}"

# 1d: 更新 trend.json
python3 "${BASEDIR}/check_stack.py" --update-trend >> "${LOG_FILE}" 2>&1 || {
    log "[Step 1/3] WARNING: --update-trend failed"
}

# 1e: 校验 latest_report.json 时间戳是否为本次运行
REPORT_TS=$(python3 -c "
import json
d=json.load(open('${REPORTS_DIR}/latest_report.json'))
print(d.get('meta',{}).get('run_at',''))
" 2>/dev/null || echo "")
# 将 TS_UTC 从 compact(20260505T005414Z) 转为 ISO(2026-05-05T00:54:14Z) 再比较
TS_ISO="${TS_UTC:0:4}-${TS_UTC:4:2}-${TS_UTC:6:2}T${TS_UTC:9:2}:${TS_UTC:11:2}:${TS_UTC:13:2}Z"
if [[ "${REPORT_TS}" != "${TS_ISO}" ]]; then
    log "[Step 1/3] WARNING: latest_report.json timestamp (${REPORT_TS}) != expected (${TS_ISO})"
fi

set -e
log "[Step 1/3] check_stack.py 完成 (exit=${CS_EXIT}, report_ts=${REPORT_TS})"

# ── Step 2: main_stack_digest.py ──
log "[Step 2/3] 执行 main_stack_digest.py (--save --no-stdout) ..."
if python3 "${BASEDIR}/main_stack_digest.py" --save --no-stdout >> "${LOG_FILE}" 2>&1; then
    log "[Step 2/3] main_stack_digest.py 完成"
else
    log "[Step 2/3] main_stack_digest.py 异常退出 code=$?"
fi

# ── Step 3: stack_watchdog.py ──
log "[Step 3/3] 执行 stack_watchdog.py ..."
if python3 "${BASEDIR}/stack_watchdog.py" --run >> "${LOG_FILE}" 2>&1; then
    log "[Step 3/3] stack_watchdog.py 完成"
else
    log "[Step 3/3] stack_watchdog.py 异常退出 code=$?"
fi

# ═══════════════════════════════════════
# 收集观察指标
# ═══════════════════════════════════════

# 提取 health_score / health_level
HEALTH_SCORE="unknown"
HEALTH_LEVEL="unknown"
if [ -f "${REPORTS_DIR}/latest_main_summary.json" ]; then
    HEALTH_SCORE=$(python3 -c "
import json,sys
d=json.load(open('${REPORTS_DIR}/latest_main_summary.json'))
print(d.get('health_score','unknown'))
" 2>/dev/null || echo "unknown")
    HEALTH_LEVEL=$(python3 -c "
import json,sys
d=json.load(open('${REPORTS_DIR}/latest_main_summary.json'))
print(d.get('health_level','unknown'))
" 2>/dev/null || echo "unknown")
fi

# 提取 trend_direction
TREND_SUMMARY="unknown"
if [ -f "${REPORTS_DIR}/trend.json" ]; then
    TREND_SUMMARY=$(python3 -c "
import json
d=json.load(open('${REPORTS_DIR}/trend.json'))
print(d.get('trend_direction','unknown'))
" 2>/dev/null || echo "unknown")
fi

# 提取 watchdog_status
WATCHDOG_STATUS="unknown"
WATCHDOG_NEW_FAIL=0
WATCHDOG_RECOVERED=0
WATCHDOG_PERSISTENT_FAIL=0
if [ -f "${REPORTS_DIR}/watchdog/watchdog_state.json" ]; then
    WATCHDOG_STATUS=$(python3 -c "
import json
d=json.load(open('${REPORTS_DIR}/watchdog/watchdog_state.json'))
print(d.get('watchdog_status','unknown'))
" 2>/dev/null || echo "unknown")
    WATCHDOG_NEW_FAIL=$(python3 -c "
import json
d=json.load(open('${REPORTS_DIR}/watchdog/watchdog_state.json'))
items=d.get('new_fail_items',[])
print(len(items) if isinstance(items,list) else 0)
" 2>/dev/null || echo "0")
    WATCHDOG_RECOVERED=$(python3 -c "
import json
d=json.load(open('${REPORTS_DIR}/watchdog/watchdog_state.json'))
items=d.get('recovered_items',[])
print(len(items) if isinstance(items,list) else 0)
" 2>/dev/null || echo "0")
    WATCHDOG_PERSISTENT_FAIL=$(python3 -c "
import json
d=json.load(open('${REPORTS_DIR}/watchdog/watchdog_state.json'))
items=d.get('persistent_fail_items',[])
print(len(items) if isinstance(items,list) else 0)
" 2>/dev/null || echo "0")
fi

# 检查 digest / watchdog 文件是否生成
DIGEST_EXISTS="false"
[ -f "${REPORTS_DIR}/digest/latest_digest.md" ] && DIGEST_EXISTS="true"
WATCHDOG_EXISTS="false"
[ -f "${REPORTS_DIR}/watchdog/latest_watchdog_summary.md" ] && WATCHDOG_EXISTS="true"

# 判断本次是否阻断 (watchdog_status 包含 blocked/red)
IS_BLOCKED="false"
if [[ "${WATCHDOG_STATUS}" == *"blocked"* ]] || [[ "${WATCHDOG_STATUS}" == *"red"* ]]; then
    IS_BLOCKED="true"
fi

# ═══════════════════════════════════════
# 写入观察记录 JSON
# ═══════════════════════════════════════

OBS_JSON="${OBS_HISTORY_DIR}/${RUN_ID}_observation.json"
export RUN_ID OBS_JSON HEALTH_SCORE HEALTH_LEVEL TREND_SUMMARY
export WATCHDOG_STATUS WATCHDOG_NEW_FAIL WATCHDOG_RECOVERED WATCHDOG_PERSISTENT_FAIL
export DIGEST_EXISTS WATCHDOG_EXISTS IS_BLOCKED OBS_DIR OBS_HISTORY_DIR
python3 << 'PYEOF'
import json, os

ts = os.environ.get('RUN_ID', '')
record = {
    'run_id': ts,
    'run_time': ts,
    'run_datetime': ts[:8] + ' ' + ts[9:11] + ':' + ts[11:13] + ':' + ts[13:15],
    'health_score': os.environ.get('HEALTH_SCORE', 'unknown'),
    'health_level': os.environ.get('HEALTH_LEVEL', 'unknown'),
    'trend_summary': os.environ.get('TREND_SUMMARY', 'unknown'),
    'watchdog_status': os.environ.get('WATCHDOG_STATUS', 'unknown'),
    'new_fail_items': int(os.environ.get('WATCHDOG_NEW_FAIL', '0')),
    'recovered_items': int(os.environ.get('WATCHDOG_RECOVERED', '0')),
    'persistent_fail_items': int(os.environ.get('WATCHDOG_PERSISTENT_FAIL', '0')),
    'digest_generated': os.environ.get('DIGEST_EXISTS', 'false') == 'true',
    'watchdog_generated': os.environ.get('WATCHDOG_EXISTS', 'false') == 'true',
    'is_blocked': os.environ.get('IS_BLOCKED', 'false') == 'true'
}
obs_json = os.environ.get('OBS_JSON', '')
with open(obs_json, 'w') as f:
    json.dump(record, f, ensure_ascii=False, indent=2)
print(json.dumps(record, ensure_ascii=False, indent=2))
PYEOF
if [ $? -ne 0 ]; then log "[ERROR] 写入观察 JSON 失败"; fi

log "观察记录已写入: ${OBS_JSON}"

# ═══════════════════════════════════════
# 更新 observation_state.json (累计汇总)
# ═══════════════════════════════════════
python3 << 'PYEOF'
import json, os, glob

state_file = os.environ['OBS_DIR'] + '/observation_state.json'
history_dir = os.environ['OBS_HISTORY_DIR']
run_id = os.environ['RUN_ID']
health_score = os.environ.get('HEALTH_SCORE', 'unknown')
health_level = os.environ.get('HEALTH_LEVEL', 'unknown')
watchdog_status = os.environ.get('WATCHDOG_STATUS', 'unknown')

records = []
for f in sorted(glob.glob(os.path.join(history_dir, '*_observation.json'))):
    try:
        with open(f) as fp:
            records.append(json.load(fp))
    except: pass

total = len(records)
success = sum(1 for r in records if not r.get('is_blocked'))
blocked = sum(1 for r in records if r.get('is_blocked'))

state = {
    'total_runs': total,
    'successful_runs': success,
    'blocked_runs': blocked,
    'latest_run_id': run_id,
    'latest_health_score': health_score,
    'latest_health_level': health_level,
    'latest_watchdog_status': watchdog_status,
    'observation_target': 7,
    'target_met': total >= 7
}

with open(state_file, 'w') as f:
    json.dump(state, f, ensure_ascii=False, indent=2)
print(f'累计: {total}次运行, {success}次正常, {blocked}次阻断, 目标:7次')
PYEOF
if [ $? -ne 0 ]; then log "[ERROR] 更新 observation_state.json 失败"; fi

# ═══════════════════════════════════════
# 生成 latest_observation_summary.md
# ═══════════════════════════════════════
python3 << 'PYEOF'
import json, os, glob

obs_dir = os.environ['OBS_DIR']
history_dir = os.environ['OBS_HISTORY_DIR']
state_file = obs_dir + '/observation_state.json'
summary_file = obs_dir + '/latest_observation_summary.md'

with open(state_file) as f:
    state = json.load(f)

records = []
for f in sorted(glob.glob(os.path.join(history_dir, '*_observation.json'))):
    try:
        with open(f) as fp:
            records.append(json.load(fp))
    except: pass

lines = []
lines.append('# 北极星计划阶段1 — 观察期巡检汇总')
lines.append('> 自动生成于每次观察巡检后 | 目标: {}次连续真实运行'.format(state['observation_target']))
lines.append('')
lines.append('- 累计运行: **{}** 次'.format(state['total_runs']))
lines.append('- 正常运行: **{}** 次'.format(state['successful_runs']))
lines.append('- 阻断运行: **{}** 次'.format(state['blocked_runs']))
remaining = state['observation_target'] - state['total_runs']
if state['target_met']:
    lines.append('- 目标达成: ✅ 是')
else:
    lines.append('- 目标达成: ❌ 否 (还差{}次)'.format(remaining))
lines.append('')
lines.append('## 最近运行记录')
lines.append('')
lines.append('| # | 时间 | 健康分 | 级别 | Watchdog | 新失败 | 恢复 | 持续失败 | 阻断 |')
lines.append('|---|------|--------|------|----------|--------|------|----------|------|')

for i, r in enumerate(records[-10:], 1):
    blocked_mark = '🚫' if r.get('is_blocked') else '✅'
    lines.append('| {} | {} | {} | {} | {} | {} | {} | {} | {} |'.format(
        i, r.get('run_time','?'), r.get('health_score','?'),
        r.get('health_level','?'), r.get('watchdog_status','?'),
        r.get('new_fail_items',0), r.get('recovered_items',0),
        r.get('persistent_fail_items',0), blocked_mark))

with open(summary_file, 'w') as f:
    f.write('\n'.join(lines) + '\n')
PYEOF
if [ $? -ne 0 ]; then log "[ERROR] 生成 observation summary 失败"; fi

log "观察期巡检完成 run_id=${RUN_ID}"
log "════════════════════════════════════════"
