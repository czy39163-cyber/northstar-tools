#!/usr/bin/env python3
"""stack_watchdog — 巡检状态看门狗，判断连续异常/持续故障/恢复状态。

只做判断，不做告警/报告生成/自动修复。
"""

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_REPORTS_DIR = os.path.join(SCRIPT_DIR, "reports", "check_stack")

INPUT_FILES = {
    "latest_main_summary.json": "latest_main_summary.json",
    "trend.json": "trend.json",
    "digest_md": os.path.join("digest", "latest_digest.md"),
    "digest_feishu": os.path.join("digest", "latest_digest_feishu.txt"),
}

# Priority order: higher index = higher priority
STATUS_PRIORITY = {
    "missing_input": 0,
    "monitoring": 1,
    "normal": 2,
    "recovery_detected": 3,
    "persistent_issue": 4,
    "warning_ready": 5,
    "blocked_ready": 6,
}


def ts_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ts_display():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def ts_compact():
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def resolve_path(base_dir, *parts):
    return os.path.join(base_dir, *parts)


def load_json(filepath):
    if not os.path.isfile(filepath):
        return None
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def load_text(filepath):
    if not os.path.isfile(filepath):
        return None
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def sanitize_path(base, sub):
    """Prevent path traversal from input file names."""
    candidate = os.path.realpath(os.path.join(base, sub))
    base_real = os.path.realpath(base)
    if os.path.commonpath([candidate, base_real]) != base_real:
        return None
    return candidate


# ---------------------------------------------------------------------------
# Input loading
# ---------------------------------------------------------------------------

def load_inputs(reports_dir):
    input_status = {}
    data = {}

    for key, rel in INPUT_FILES.items():
        path = sanitize_path(reports_dir, rel)
        if path is None:
            input_status[key] = "missing"
            data[key] = None
            continue

        if key in ("latest_main_summary.json", "trend.json"):
            val = load_json(path)
            input_status[key] = "ok" if val is not None else "missing"
            data[key] = val
        else:
            val = load_text(path)
            input_status[key] = "ok" if val is not None else "missing"
            data[key] = val

    return input_status, data


# ---------------------------------------------------------------------------
# Consecutive health level counting from trend.json runs
# ---------------------------------------------------------------------------

def count_consecutive_health(runs):
    """From newest → oldest, count consecutive same health_level.

    runs may be chronologically sorted.  Sort by run_at descending first,
    then count how many times the most recent health_level repeats consecutively.
    """
    if not runs:
        return {"green": 0, "yellow": 0, "red": 0}

    sorted_runs = sorted(runs, key=lambda r: r.get("run_at", ""), reverse=True)
    counts = {"green": 0, "yellow": 0, "red": 0}

    if not sorted_runs:
        return counts

    current_level = sorted_runs[0].get("health_level", "")
    streak = 0
    for r in sorted_runs:
        if r.get("health_level", "") == current_level:
            streak += 1
        else:
            break

    counts[current_level] = streak
    return counts


# ---------------------------------------------------------------------------
# Rule evaluation
# ---------------------------------------------------------------------------

def _persistent_item_names(persistent_fail_items):
    """Extract stable names from persistent_fail_items list."""
    if not persistent_fail_items:
        return []
    names = []
    for item in persistent_fail_items:
        cat = item.get("category", "")
        name = item.get("name", "")
        names.append(f"{cat}/{name}")
    return sorted(names)


def evaluate_rules(input_status, main_summary, trend_data, previous_state):
    """Apply trigger rules and return the highest-priority status + metadata.

    Returns (watchdog_status, triggered_rules, details)
    """
    missing_inputs = [k for k, v in input_status.items() if v != "ok"]

    # Edge: all inputs missing
    if all(v == "missing" for v in input_status.values()):
        return "missing_input", ["all_input_missing"], {
            "missing_inputs": missing_inputs,
        }

    # Edge: trend.json runs empty
    runs = trend_data.get("runs", []) if trend_data else []
    if not runs and main_summary is None:
        return "missing_input", ["all_input_missing"], {
            "missing_inputs": missing_inputs,
        }
    if not runs:
        return "monitoring", ["no_history"], {"missing_inputs": missing_inputs}

    consecutive = count_consecutive_health(runs)

    health_level = main_summary.get("health_level", "green") if main_summary else "green"
    health_score = main_summary.get("health_score", 100) if main_summary else 100
    persistent_items = main_summary.get("persistent_fail_items", []) if main_summary else []
    recovered_items = main_summary.get("recovered_items", []) if main_summary else []

    persistent_names = _persistent_item_names(persistent_items)
    prev_persistent_count = 0
    prev_persistent_names = []
    if previous_state:
        prev_persistent_count = previous_state.get("persistent_fail_run_count", 0)
        prev_persistent_names = previous_state.get("persistent_fail_names", [])

    # Determine if persistent items are "continuing" from previous run
    has_persistent_overlap = bool(persistent_names) and bool(
        set(persistent_names) & set(prev_persistent_names)
    )
    # If current has persistent items and at least some overlap with prev, increment count
    if persistent_names and has_persistent_overlap:
        persistent_run_count = prev_persistent_count + 1
    elif persistent_names:
        persistent_run_count = 1
    else:
        persistent_run_count = 0

    details = {
        "consecutive": consecutive,
        "persistent_run_count": persistent_run_count,
        "persistent_names": persistent_names,
        "recovered_items": recovered_items,
        "missing_inputs": missing_inputs,
        "health_level": health_level,
        "health_score": health_score,
    }

    triggered = []

    # Priority: blocked_ready (consecutive 2× red)
    if consecutive.get("red", 0) >= 2:
        triggered.append("consecutive_red_x2")
        return "blocked_ready", triggered, details

    # Priority: warning_ready (consecutive 3× yellow)
    if consecutive.get("yellow", 0) >= 3:
        triggered.append("consecutive_yellow_x3")
        return "warning_ready", triggered, details

    # Priority: persistent_issue
    if persistent_run_count >= 3:
        triggered.append("persistent_fail_x3")
        return "persistent_issue", triggered, details

    # Priority: recovery_detected
    if recovered_items:
        triggered.append("recovery_detected")
        return "recovery_detected", triggered, details

    # Priority: normal
    if health_level == "green" and not persistent_items:
        triggered.append("green_clean")
        return "normal", triggered, details

    # Default
    triggered.append("no_rule_matched")
    return "monitoring", triggered, details


# ---------------------------------------------------------------------------
# Status change detection
# ---------------------------------------------------------------------------

def detect_status_change(previous_status, current_status):
    if previous_status is None:
        return None  # will be rendered as "first_run" upstream
    if previous_status == current_status:
        return "stable"
    if STATUS_PRIORITY.get(current_status, 0) > STATUS_PRIORITY.get(previous_status, 0):
        return "escalated"
    return "deescalated"


# ---------------------------------------------------------------------------
# Output generation
# ---------------------------------------------------------------------------

EMOJI_STATUS = {
    "normal": "🟢",
    "warning_ready": "🟡",
    "blocked_ready": "🔴",
    "recovery_detected": "✅",
    "persistent_issue": "⚠️",
    "monitoring": "🔵",
    "missing_input": "⚫",
}


def build_watchdog_state(
    run_at,
    watchdog_status,
    current_health_level,
    current_health_score,
    consecutive_counts,
    triggered_rules,
    persistent_names,
    persistent_run_count,
    recovered_items,
    input_status,
    previous_status,
    is_first_run,
    status_change,
):
    return {
        "run_at": run_at,
        "watchdog_status": watchdog_status,
        "current_health_level": current_health_level,
        "current_health_score": current_health_score,
        "consecutive_counts": consecutive_counts,
        "triggered_rules": triggered_rules,
        "persistent_fail_names": persistent_names,
        "persistent_fail_run_count": persistent_run_count,
        "recovered_items": recovered_items,
        "input_status": input_status,
        "previous_status": previous_status,
        "is_first_run": is_first_run,
        "status_change": status_change,
    }


def build_markdown_summary(state):
    lines = []
    run_display = state["run_at"]
    # Convert ISO to display format
    try:
        dt = datetime.fromisoformat(state["run_at"].replace("Z", "+00:00"))
        run_display = dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, AttributeError):
        pass

    emoji = EMOJI_STATUS.get(state["watchdog_status"], "⚪")
    status = state["watchdog_status"]

    lines.append(f"🐕 **Watchdog 巡检判断**")
    lines.append(
        f"判断时间: {run_display} | 状态: {emoji} {status}"
    )
    lines.append(
        f"当前健康: {state['current_health_level']} ({state['current_health_score']}分)"
        f" | 连续: {state['consecutive_counts'].get(state['current_health_level'], 0)}次"
        f" {state['current_health_level']}"
    )
    lines.append("")

    cc = state["consecutive_counts"]
    lines.append("📊 **连续计数**:")
    lines.append(f"- green: {cc.get('green', 0)}次")
    lines.append(f"- yellow: {cc.get('yellow', 0)}次")
    lines.append(f"- red: {cc.get('red', 0)}次")
    lines.append("")

    triggered = state["triggered_rules"]
    if triggered:
        lines.append(f"📋 **触发规则**: {', '.join(triggered)}")
    else:
        lines.append("📋 **触发规则**: (无)")
    lines.append("")

    recovered = state["recovered_items"]
    if recovered:
        names = [f"{i['category']}/{i['name']}" for i in recovered]
        lines.append(f"✅ **恢复检测**: {', '.join(names)}")
    else:
        lines.append("✅ **恢复检测**: (本轮无)")
    lines.append("")

    persistent = state["persistent_fail_names"]
    if persistent:
        lines.append(
            f"⚠️ **持续故障**: {', '.join(persistent)}"
            f" (连续 {state['persistent_fail_run_count']} 次)"
        )
    else:
        lines.append("⚠️ **持续故障**: (无)")
    lines.append("")

    sc = state["status_change"]
    if sc == "first_run":
        sc_text = "first_run (首次运行)"
    elif sc == "stable":
        sc_text = "stable (状态不变)"
    elif sc == "escalated":
        sc_text = f"escalated ({state['previous_status']} → {state['watchdog_status']})"
    elif sc == "deescalated":
        sc_text = f"deescalated ({state['previous_status']} → {state['watchdog_status']})"
    else:
        sc_text = str(sc)
    lines.append(f"💡 **状态变化**: {sc_text}")
    lines.append("")

    # Input file status
    input_missing = [k for k, v in state["input_status"].items() if v != "ok"]
    if input_missing:
        lines.append(f"⚠️ **缺失输入**: {', '.join(input_missing)}")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="stack_watchdog — 巡检状态看门狗"
    )
    parser.add_argument(
        "--run", action="store_true", default=True, help="执行一次 watchdog 判断（默认）"
    )
    parser.add_argument("--output-dir", default=None, help="指定输出目录")
    parser.add_argument(
        "--status",
        action="store_true",
        default=False,
        help="仅打印当前 watchdog_status",
    )
    args = parser.parse_args()

    reports_dir = args.output_dir or DEFAULT_REPORTS_DIR

    # Load inputs
    input_status, data = load_inputs(reports_dir)

    main_summary = data.get("latest_main_summary.json")
    trend_data = data.get("trend.json")

    # Load previous watchdog state
    watchdog_dir = os.path.join(reports_dir, "watchdog")
    prev_state_path = os.path.join(watchdog_dir, "watchdog_state.json")
    previous_state = load_json(prev_state_path)

    is_first_run = previous_state is None
    previous_status = previous_state.get("watchdog_status") if previous_state else None

    # Evaluate rules
    watchdog_status, triggered_rules, details = evaluate_rules(
        input_status, main_summary, trend_data, previous_state
    )

    current_health_level = details.get("health_level", "green")
    current_health_score = details.get("health_score", 0)
    consecutive_counts = details.get("consecutive", {"green": 0, "yellow": 0, "red": 0})
    persistent_names = details.get("persistent_names", [])
    persistent_run_count = details.get("persistent_run_count", 0)
    recovered_items = details.get("recovered_items", [])

    # Detect status change
    status_change = detect_status_change(previous_status, watchdog_status)
    if is_first_run:
        status_change_label = "first_run"
    else:
        status_change_label = status_change

    # --status mode: print and exit
    if args.status:
        print(watchdog_status)
        sys.exit(0 if watchdog_status == "normal" else 1)

    run_at = ts_now()

    state = build_watchdog_state(
        run_at=run_at,
        watchdog_status=watchdog_status,
        current_health_level=current_health_level,
        current_health_score=current_health_score,
        consecutive_counts=consecutive_counts,
        triggered_rules=triggered_rules,
        persistent_names=persistent_names,
        persistent_run_count=persistent_run_count,
        recovered_items=recovered_items,
        input_status=input_status,
        previous_status=previous_status,
        is_first_run=is_first_run,
        status_change=status_change_label,
    )

    # Write outputs
    ensure_dir(watchdog_dir)

    # 1. watchdog_state.json
    state_path = os.path.join(watchdog_dir, "watchdog_state.json")
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
        f.write("\n")

    # 2. latest_watchdog_summary.txt (plain text, no markdown)
    txt_path = os.path.join(watchdog_dir, "latest_watchdog_summary.txt")
    md_text = build_markdown_summary(state)
    # Strip markdown formatting for plain text
    txt_text = md_text.replace("**", "")
    # Remove extra blank lines (more than 1 consecutive)
    import re
    txt_text = re.sub(r"\n{3,}", "\n\n", txt_text)
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(txt_text)
        f.write("\n")

    # 3. latest_watchdog_summary.md
    md_path = os.path.join(watchdog_dir, "latest_watchdog_summary.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_text)
        f.write("\n")

    # 4. history/<TIMESTAMP>_watchdog.json
    history_dir = os.path.join(watchdog_dir, "history")
    ensure_dir(history_dir)
    history_path = os.path.join(history_dir, f"{ts_compact()}_watchdog.json")
    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
        f.write("\n")

    # Print summary to stdout
    print(md_text)

    # Exit code
    sys.exit(0)


if __name__ == "__main__":
    main()
