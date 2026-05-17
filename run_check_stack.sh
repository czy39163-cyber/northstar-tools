#!/usr/bin/env bash
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPORTS_DIR="${SCRIPT_DIR}/reports/check_stack"
HISTORY_DIR="${REPORTS_DIR}/history"
TIMESTAMP=$(date -u +%Y%m%dT%H%M%SZ)

mkdir -p "${REPORTS_DIR}"
mkdir -p "${HISTORY_DIR}"

# Step 1: timestamped full report — capture business exit code
python3 "${SCRIPT_DIR}/check_stack.py" --json --output "${REPORTS_DIR}/${TIMESTAMP}.json" "$@"
BUSINESS_EXIT=$?

# check_stack.py signal for its own fatal error
if [ "${BUSINESS_EXIT}" -eq 2 ]; then
    echo "FATAL: check_stack.py exited with code 2"
    exit 2
fi

# Step 2: update latest_report.json
cp "${REPORTS_DIR}/${TIMESTAMP}.json" "${REPORTS_DIR}/latest_report.json" || {
    echo "FATAL: failed to copy latest_report.json"
    exit 2
}

# Step 3: copy to history/ (ISO timestamp filename)
cp "${REPORTS_DIR}/${TIMESTAMP}.json" "${HISTORY_DIR}/${TIMESTAMP}.json" || {
    echo "WARNING: failed to copy to history"
}

# Step 4: generate latest_summary.txt (human-readable text)
python3 "${SCRIPT_DIR}/check_stack.py" --summary-text "$@" > "${REPORTS_DIR}/latest_summary.txt"
SUMMARY_TEXT_EXIT=$?
if [ "${SUMMARY_TEXT_EXIT}" -eq 2 ]; then
    echo "FATAL: failed to generate latest_summary.txt (script error)"
    exit 2
fi

# Step 5: generate latest_main_summary.json (MAIN-consumable JSON)
python3 "${SCRIPT_DIR}/check_stack.py" --summary-json "$@" > "${REPORTS_DIR}/latest_main_summary.json"
SUMMARY_JSON_EXIT=$?
if [ "${SUMMARY_JSON_EXIT}" -eq 2 ]; then
    echo "FATAL: failed to generate latest_main_summary.json (script error)"
    exit 2
fi

# Step 6: update trend.json (reads latest_report.json + history/)
python3 "${SCRIPT_DIR}/check_stack.py" --update-trend
TREND_EXIT=$?
if [ "${TREND_EXIT}" -eq 2 ]; then
    echo "WARNING: failed to update trend.json"
fi

echo "Report:  ${REPORTS_DIR}/${TIMESTAMP}.json"
echo "Latest:  ${REPORTS_DIR}/latest_report.json"
echo "Summary: ${REPORTS_DIR}/latest_summary.txt"
echo "History: ${HISTORY_DIR}/${TIMESTAMP}.json"
echo "Trend:   ${REPORTS_DIR}/trend.json"

exit "${BUSINESS_EXIT}"
