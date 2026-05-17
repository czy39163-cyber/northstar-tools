#!/usr/bin/env python3
"""GPT-MAIN Loop Utilities — Shared data structures and safety tools.

Phase 1: Bridge瘦身后，本文件仅保留可复用工具函数和常量。
GptLoopEngine 已删除，由 gpt_loop_controller.py 替代。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_ROUNDS = 50
COMPACT_THRESHOLD = 10
RECENT_ROUNDS_KEEP = 3
MAIN_API_URL = "http://127.0.0.1:18642/v1/chat/completions"
MAIN_API_TIMEOUT = 300

# Parsing patterns
RE_AT_MAIN = re.compile(r"@MAIN:\s*(.+?)(?=\n##|\n@MAIN:|$)", re.DOTALL)
RE_TASK_DONE = re.compile(r"##TASK_DONE##")
RE_PROJECT_CLOSED = re.compile(r"##PROJECT_CLOSED##")

# Feishu wrapper patterns to strip
RE_FEISHU_PREFIX = re.compile(
    r"^(?:<at[^>]*>.*?</at>\s*)*"          # <at> tags
    r"(?:@[^:\s]*\s+)?"                       # @mentions (not @MAIN:)
    r"(?:ChatGPT\s*(?:回复|Response)[：:]\s*)?"  # ChatGPT prefix
    r"(?:[-—]+\s*ChatGPT\s+Feishu\s+Bridge\s*[-—]+\s*)?",  # bridge header
    re.IGNORECASE | re.DOTALL,
)
RE_FEISHU_SUFFIX = re.compile(
    r"\s*[-—]+\s*ChatGPT\s+Feishu\s+Bridge\s*[-—]*",
    re.IGNORECASE,
)

# Safety check patterns
R1_FORBIDDEN = [
    r"\bapi[_-]?key\b", r"\btoken\b", r"\bsecret\b", r"\bpassword\b",
    r"\.env\b", r"\bcredential\b", r"真值源", r"\b广播.*飞书\b",
    r"\bannounce\b.*\bfeishu\b", r"\ball[_-]?staff\b",
]
R3_VAGUE = [
    r"\bmaybe\b", r"\btry\b.*\bsee\b", r"\bif\s+possible\b",
    r"看看.*能不能", r"试试", r"maybe.*try",
]

RE_R1 = re.compile("|".join(R1_FORBIDDEN), re.IGNORECASE)
RE_R3 = re.compile("|".join(R3_VAGUE), re.IGNORECASE)

# Negation words that indicate R1 hits are in a safety reminder, not a real violation
_RE_NEGATION = re.compile(
    r"(?:不要|不读|不碰|不许|不输出|不读取|不得|禁止|请勿|不要读取|不要输出"
    r"|don'?t\s+(?:read|output|access|touch|modify)"
    r"|never\s+(?:read|output|access)"
    r"|do\s+not\s+(?:read|output|access|touch|modify))",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class RoundRecord:
    """Record of a single GPT→MAIN round in the loop."""
    round_num: int
    gpt_instruction: str
    main_instruction: str
    main_result: str
    status: str  # "completed" | "failed" | "skipped" | "refused"
    timestamp: str


# ---------------------------------------------------------------------------
# Utility Functions
# ---------------------------------------------------------------------------

def check_safety(instruction: str, task: str = "") -> dict:
    """Apply R1/R2/R3 safety rules.

    Args:
        instruction: The @MAIN: instruction text from GPT.
        task: The original task description (optional, used for R2 deviation check).

    Returns:
        dict with keys: level ("low"|"medium"|"high"), rule, reason.
    """
    # R1: Boundary check
    m_r1 = RE_R1.search(instruction)
    if m_r1:
        # Check if the hit is inside a safety reminder (negation context).
        # GPT often says "不要读 .env / 不输出 API key" — that's a guard, not a violation.
        prefix = instruction[:m_r1.start()][-40:]  # up to 40 chars before the match
        if _RE_NEGATION.search(prefix):
            return {"level": "medium", "rule": "R1_boundary_negated",
                    "reason": "指令含否定语境的安全提醒，降级为警告"}
        # Only flag as HIGH if an action verb is near the sensitive keyword.
        context = instruction[max(0, m_r1.start() - 30):m_r1.end() + 30]
        if re.search(
            r"(?:读取|输出|修改|访问|调用|执行.*密钥|read|output|modify|access|call.*key|run.*env)",
            context, re.IGNORECASE,
        ):
            return {"level": "high", "rule": "R1_boundary",
                    "reason": "指令含主动读取/输出/修改敏感信息"}
        return {"level": "medium", "rule": "R1_mention",
                "reason": "指令提及敏感词但无主动操作意图，降级为警告"}

    # R3: Uncertainty check (runs before R2 because vague high-risk instructions need flagging)
    if RE_R3.search(instruction) and len(instruction) < 200:
        return {"level": "medium", "rule": "R3_uncertainty",
                "reason": "指令模糊或低信心试探"}

    # R2: Deviation check — compare instruction against task
    if task:
        task_words = set(task.lower().split())
        inst_words = set(instruction.lower().split())
        if len(inst_words) > 3 and task_words:
            overlap = task_words & inst_words
            if not overlap:
                return {"level": "medium", "rule": "R2_deviation",
                        "reason": "指令与任务主线无关键词重叠"}

    return {"level": "low", "rule": None, "reason": None}


def strip_feishu_wrapper(text: str) -> str:
    """Remove Feishu/Bridge formatting wrappers from GPT response text."""
    text = RE_FEISHU_PREFIX.sub("", text).strip()
    text = RE_FEISHU_SUFFIX.sub("", text).strip()
    return text
