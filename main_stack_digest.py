#!/usr/bin/env python3
"""生成 MAIN / 飞书可读的中文巡检摘要。

读取 reports/check_stack/ 下的 JSON 文件，生成格式化的 Markdown 巡检摘要。
纯 Python3，无第三方依赖。
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

REPORTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports", "check_stack")

LEVEL_EMOJI = {"green": "\U0001f7e2", "yellow": "\U0001f7e1", "red": "\U0001f534"}


def load_json(filename):
    path = os.path.join(REPORTS_DIR, filename)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"[WARN] 文件不存在，跳过: {path}", file=sys.stderr)
        return None
    except json.JSONDecodeError as e:
        print(f"[WARN] JSON 解析失败: {path}: {e}", file=sys.stderr)
        return None


def fmt_time(iso_str):
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, AttributeError):
        return iso_str


def compress_trend(runs):
    """将连续相同 health_level+score 的运行压缩为摘要。"""
    if not runs:
        return ""
    groups = []
    for run in runs:
        key = (run.get("health_level", "?"), run.get("health_score", "?"))
        if groups and groups[-1][0] == key:
            groups[-1][1] += 1
        else:
            groups.append([key, 1])
    parts = []
    for (level, score), count in groups:
        parts.append(f"{count}次 {level}({score}分)")
    return " → ".join(parts)


def section(title, lines):
    """生成一个段落。如果 lines 为空则返回空字符串。"""
    if not lines:
        return ""
    body = "\n".join(f"- {l}" for l in lines)
    return f"\n**{title}**:\n{body}\n"


def format_items(items, show_detail=True):
    """格式化 fail/recovered 条目列表。"""
    result = []
    for item in items:
        cat = item.get("category", "?")
        name = item.get("name", "?")
        detail = item.get("detail", "")
        if show_detail and detail:
            result.append(f"{cat}/{name}: {detail}")
        else:
            result.append(f"{cat}/{name}")
    return result


def strip_markdown_bold(text):
    """去除 ** 标记。"""
    return text.replace("**", "")


def strip_emoji(text):
    """去除 emoji 字符。"""
    emoji_pattern = re.compile(
        "["
        "\U0001F300-\U0001F5FF"
        "\U0001F600-\U0001F64F"
        "\U0001F680-\U0001F6FF"
        "\U0001F1E0-\U0001F1FF"
        "\U0001F7E0-\U0001F7FF"
        "\U0001F900-\U0001F9FF"
        "\U0001FA00-\U0001FA6F"
        "\U0001FA70-\U0001FAFF"
        "☀-➿"
        "︀-️"
        "‍"
        "]+", flags=re.UNICODE)
    return emoji_pattern.sub("", text).strip()


def compress_blank_lines(text):
    """将 3 个及以上连续换行压缩为 2 个（单个空行）。"""
    return re.sub(r'\n{3,}', '\n\n', text)


def generate(use_summary=True, use_trend=False, use_report=False):
    summary = load_json("latest_main_summary.json") if use_summary else None
    trend = load_json("trend.json") if use_trend else None
    report = load_json("latest_report.json") if use_report else None

    # 优先从 report.meta 取时间和版本，fallback 到 summary
    version = "?"
    run_at = ""
    hostname = "?"
    if report and report.get("meta"):
        meta = report["meta"]
        version = meta.get("version", summary.get("version", "?") if summary else "?")
        run_at = fmt_time(meta.get("run_at", ""))
        hostname = meta.get("hostname", "?")
    elif summary:
        version = summary.get("version", "?")
        run_at = ""  # summary 没有 run_at

    # 从 summary 或 report.health_info 取健康数据
    health_score = None
    health_level = None
    fail_items = []
    warnings = []
    recovered = []
    persistent = []
    new_fail = []
    trend_summary = ""
    decision_hint = ""
    checks_run = []
    ok_count = 0
    fail_count = 0
    status = "?"
    tool_name = "check_stack"

    if summary:
        tool_name = summary.get("tool_name", "check_stack")
        health_score = summary.get("health_score")
        health_level = summary.get("health_level", "?")
        fail_items = summary.get("fail_items", [])
        warnings = summary.get("warnings", [])
        recovered = summary.get("recovered_items", [])
        persistent = summary.get("persistent_fail_items", [])
        new_fail = summary.get("new_fail_items", [])
        trend_summary = summary.get("trend_summary", "")
        decision_hint = summary.get("main_decision_hint", "")
        checks_run = summary.get("checks_run", [])
        ok_count = summary.get("ok", 0)
        fail_count = summary.get("fail", 0)
        status = summary.get("status", "?")
    elif report and report.get("health_info"):
        hi = report["health_info"]
        health_score = hi.get("health_score")
        health_level = hi.get("health_level", "?")
        recovered = hi.get("recovered_items", [])
        persistent = hi.get("persistent_fail_items", [])
        new_fail = hi.get("new_fail_items", [])
        trend_summary = hi.get("trend_summary", "")
        decision_hint = hi.get("main_decision_hint", "")
    elif report:
        health_score = report.get("health_score")
        health_level = report.get("health_level", "?")
        s = report.get("summary", {})
        ok_count = s.get("ok", 0)
        fail_count = s.get("fail", 0)
        status = s.get("status", "?")
        checks_run = s.get("checks_run", [])

    # 构建检查项摘要
    check_parts = []
    for c in checks_run:
        check_parts.append(f"{c}")
    checks_str = ", ".join(check_parts)

    # --- 构建输出 ---
    lines = []

    # 标题行
    emoji = LEVEL_EMOJI.get(health_level, "❓")
    lines.append(f"{emoji} **Hermes 环境巡检摘要**")

    # 版本和时间
    meta_parts = [f"版本: {tool_name} v{version}"]
    if run_at:
        meta_parts.append(f"检查时间: {run_at}")
    lines.append(" | ".join(meta_parts))

    # 健康分数
    score_str = f"{health_score}/100" if health_score is not None else "?"
    lines.append(f"健康分数: **{score_str}** ({health_level}) | 状态: {status}")
    lines.append(f"检查项: {checks_str}({ok_count}项通过, {fail_count}项失败)")

    # 趋势（来自 trend.json）
    if trend:
        comp = trend.get("comparison", {})
        prev_score = comp.get("previous_health_score", "?")
        prev_level = comp.get("previous_health_level", "?")
        cur_score = comp.get("current_health_score", "?")
        cur_level = comp.get("current_health_level", "?")
        direction = comp.get("trend_direction", trend.get("trend_direction", ""))
        lines.append(f"\n\U0001f4ca **趋势**: {direction} ({prev_score}→{cur_score}, {prev_level}→{cur_level})")

        runs = trend.get("runs", [])
        if runs:
            compressed = compress_trend(runs)
            lines.append(f"- 最近 {len(runs)} 次运行: {compressed}")

    # 恢复项
    if recovered:
        lines.append(f"\n✅ **恢复项**: (本轮从失败恢复为正常的项)")
        for item in recovered:
            cat = item.get("category", "?")
            name = item.get("name", "?")
            detail = item.get("detail", "")
            lines.append(f"- {cat}/{name}: {detail} → 已恢复")
    else:
        lines.append(f"\n✅ **恢复项**: (本轮无)")

    # 持续失败项
    if persistent:
        lines.append(f"\n⚠️ **持续失败项**:")
        for item in persistent:
            cat = item.get("category", "?")
            name = item.get("name", "?")
            detail = item.get("detail", "")
            lines.append(f"- {cat}/{name}: {detail}")
    else:
        lines.append(f"\n⚠️ **持续失败项**: (本轮无)")

    # 新增失败项
    if new_fail:
        lines.append(f"\n🔴 **新增失败项**:")
        for item in new_fail:
            cat = item.get("category", "?")
            name = item.get("name", "?")
            detail = item.get("detail", "")
            lines.append(f"- {cat}/{name}: {detail}")
    else:
        lines.append(f"\n🔴 **新增失败项**: (本轮无)")

    # 警告
    if warnings:
        lines.append(f"\n⚡ **警告**:")
        for w in warnings:
            if isinstance(w, str):
                lines.append(f"- {w}")
            else:
                lines.append(f"- {w.get('name', w.get('detail', str(w)))}")

    # 详细报告（--with-report）
    if report:
        proc = report.get("process")
        if proc:
            running = "✅ 运行中" if proc.get("running") else "❌ 未运行"
            detail = proc.get("detail", "")
            # 截断过长的 detail
            if len(detail) > 120:
                detail = detail[:117] + "..."
            lines.append(f"\n📋 **进程**: {proc.get('name', '?')} {running}")
            if detail:
                lines.append(f"  {detail}")

        ports = report.get("ports", [])
        if ports:
            lines.append(f"\n🔌 **端口检查**:")
            for p in ports:
                lines.append(f"- {p.get('port', '?')}: {p.get('status', '?')}")

        config_files = report.get("config_files", {})
        if config_files:
            lines.append(f"\n📁 **配置文件检查**:")
            for name, info in config_files.items():
                if isinstance(info, dict):
                    exists = "✅ 存在" if info.get("exists") else "❌ 不存在"
                    found = info.get("found", [])
                    if found:
                        exists += f" ({', '.join(found)})"
                    lines.append(f"- {name}: {exists}")
                else:
                    lines.append(f"- {name}: {info}")

        env_vars = report.get("env_vars", {})
        if env_vars:
            lines.append(f"\n🔑 **环境变量**: (值已脱敏)")
            for category, vars_list in env_vars.items():
                if isinstance(vars_list, list) and vars_list:
                    # 只显示 key 名，不暴露值
                    var_names = []
                    for v in vars_list:
                        if isinstance(v, dict):
                            var_names.append(v.get("name", "?"))
                        elif isinstance(v, str):
                            var_names.append(v)
                    lines.append(f"- {category}: {', '.join(var_names)} (已设置)")
                elif isinstance(vars_list, list):
                    lines.append(f"- {category}: (无)")

        http_checks = report.get("http_checks", [])
        if http_checks:
            lines.append(f"\n🌐 **HTTP 检查**:")
            for hc in http_checks:
                status = "✅" if hc.get("ok") else "❌"
                lines.append(f"- {status} {hc.get('name', hc.get('url', '?'))}")

        rec_actions = report.get("recommended_actions", [])
        if rec_actions:
            lines.append(f"\n🔧 **建议操作**:")
            for a in rec_actions:
                lines.append(f"- {a}")

    # 决策提示
    if decision_hint:
        lines.append(f"\n💡 **MAIN 决策提示**: {decision_hint}")

    # 仅摘要模式时的趋势文本
    if not trend and trend_summary:
        lines.append(f"\n📊 **趋势摘要**: {trend_summary}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="生成 MAIN / 飞书可读的中文巡检摘要"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--summary-only", action="store_true", help="仅使用 latest_main_summary.json")
    group.add_argument("--with-trend", action="store_true", help="使用 summary + trend.json")
    group.add_argument("--with-report", action="store_true", help="使用 summary + latest_report.json")
    group.add_argument("--all", action="store_true", help="使用所有三个文件（默认）")
    parser.add_argument("--output-dir", default=None, help="文件输出目录（默认: reports/check_stack/digest/）")
    parser.add_argument("--no-stdout", action="store_true", help="不打印到终端（仅落盘）")
    parser.add_argument("--save", action="store_true", help="启用文件落盘")
    args = parser.parse_args()

    if args.summary_only:
        use_summary, use_trend, use_report = True, False, False
    elif args.with_trend:
        use_summary, use_trend, use_report = True, True, False
    elif args.with_report:
        use_summary, use_trend, use_report = True, False, True
    else:
        use_summary, use_trend, use_report = True, True, True

    output = generate(use_summary=use_summary, use_trend=use_trend, use_report=use_report)

    if args.save:
        out_dir = args.output_dir or os.path.join(REPORTS_DIR, "digest")
        history_dir = os.path.join(out_dir, "history")
        os.makedirs(history_dir, exist_ok=True)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        # latest_digest.md — 完整 Markdown（与 generate() 输出一致）
        md_path = os.path.join(out_dir, "latest_digest.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(output + "\n")
        print(f"[digest] {md_path}", file=sys.stderr)

        # latest_digest.txt — 纯文本（去除 ** 和 emoji）
        plain = strip_emoji(strip_markdown_bold(output))
        txt_path = os.path.join(out_dir, "latest_digest.txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(plain + "\n")
        print(f"[digest] {txt_path}", file=sys.stderr)

        # latest_digest_feishu.txt — 飞书格式（去除 **，保留 emoji，压缩空行）
        feishu = compress_blank_lines(strip_markdown_bold(output))
        feishu_path = os.path.join(out_dir, "latest_digest_feishu.txt")
        with open(feishu_path, "w", encoding="utf-8") as f:
            f.write(feishu + "\n")
        print(f"[digest] {feishu_path}", file=sys.stderr)

        # history/YYYYMMDD_HHMMSS_digest.md — 历史归档副本
        hist_path = os.path.join(history_dir, f"{ts}_digest.md")
        with open(hist_path, "w", encoding="utf-8") as f:
            f.write(output + "\n")
        print(f"[digest] {hist_path}", file=sys.stderr)

    if not args.no_stdout:
        print(output)


if __name__ == "__main__":
    main()
