from __future__ import annotations

import json
from pathlib import Path

from planectra.models import ConversationTurn


def is_in_plan_mode(transcript_path: str) -> bool:
    """Check if session is currently in plan mode by scanning the transcript tail."""
    path = Path(transcript_path)
    if not path.exists():
        return False

    size = path.stat().st_size
    read_size = min(size, 200 * 1024)  # Last 200KB

    last_event = None
    with open(path, "rb") as f:
        if size > read_size:
            f.seek(size - read_size)
        data = f.read().decode("utf-8", errors="replace")

    lines = data.split("\n")
    if size > read_size:
        lines = lines[1:]  # Skip partial first line

    parsed = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            parsed.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    for obj in parsed:
        last_event = _check_plan_event(obj, last_event)

    if last_event == "EnterPlanMode":
        return True
    if last_event == "ExitPlanMode":
        return False

    # No tool-based plan events found — check the last user entry's
    # permissionMode field (covers user-toggled plan mode via Shift+Tab / /plan)
    for obj in reversed(parsed):
        if obj.get("type") == "user" and "permissionMode" in obj:
            return obj["permissionMode"] == "plan"

    return False


def _check_plan_event(obj: dict, current: str | None) -> str | None:
    """Check if a transcript entry contains a plan mode tool use."""
    if obj.get("type") != "assistant":
        return current

    content = obj.get("message", {}).get("content", [])
    if not isinstance(content, list):
        return current

    for block in content:
        if isinstance(block, dict) and block.get("type") == "tool_use":
            name = block.get("name", "")
            if name in ("EnterPlanMode", "ExitPlanMode"):
                return name
    return current


def extract_initial_prompt(transcript_path: str) -> str:
    """Extract the user message that triggered the last EnterPlanMode.

    Scans backward from the last EnterPlanMode to find the preceding
    non-meta user message.
    """
    path = Path(transcript_path)
    if not path.exists():
        return ""

    entries = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    # Find the last EnterPlanMode
    plan_start = None
    for i, entry in enumerate(entries):
        if entry.get("type") == "assistant":
            content = entry.get("message", {}).get("content", [])
            if isinstance(content, list):
                for block in content:
                    if (isinstance(block, dict)
                            and block.get("type") == "tool_use"
                            and block.get("name") == "EnterPlanMode"):
                        plan_start = i

    if plan_start is None:
        return ""

    # Search backward for the user message that triggered it
    for i in range(plan_start - 1, -1, -1):
        entry = entries[i]
        if entry.get("type") == "user":
            text = entry.get("message", {}).get("content", "")
            if isinstance(text, str) and text.strip() and not entry.get("isMeta"):
                return text.strip()
        elif entry.get("type") == "assistant":
            break
    return ""


def extract_plan_conversation(transcript_path: str) -> dict:
    """Extract the last complete plan conversation from the transcript.

    Returns dict with:
        - conversation: list of ConversationTurn
        - plan_content: str (last assistant plan text)
        - initial_prompt: str (first user message in plan mode)
        - num_attempts: int
    """
    path = Path(transcript_path)
    if not path.exists():
        return {"conversation": [], "plan_content": "", "initial_prompt": "", "num_attempts": 0}

    entries = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    # Find the last EnterPlanMode / ExitPlanMode boundaries
    plan_start = None
    plan_end = None
    for i, entry in enumerate(entries):
        if entry.get("type") == "assistant":
            content = entry.get("message", {}).get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        if block.get("name") == "EnterPlanMode":
                            plan_start = i
                            plan_end = None
                        elif block.get("name") == "ExitPlanMode":
                            plan_end = i

    if plan_start is None:
        return {"conversation": [], "plan_content": "", "initial_prompt": "", "num_attempts": 0}

    # Search backward for the user message that triggered EnterPlanMode
    pre_plan_prompt = ""
    if plan_start > 0:
        for i in range(plan_start - 1, -1, -1):
            entry = entries[i]
            if entry.get("type") == "user":
                text = entry.get("message", {}).get("content", "")
                if isinstance(text, str) and text.strip() and not entry.get("isMeta"):
                    pre_plan_prompt = text.strip()
                    break
            elif entry.get("type") == "assistant":
                break  # don't go past previous assistant turn

    end_idx = plan_end if plan_end is not None else len(entries)
    plan_entries = entries[plan_start : end_idx + 1]

    conversation: list[ConversationTurn] = []
    initial_prompt = ""
    plan_content = ""
    attempt = 0

    for entry in plan_entries:
        msg_type = entry.get("type")

        if msg_type == "user":
            text = entry.get("message", {}).get("content", "")
            if isinstance(text, str) and text.strip():
                # Skip meta/system messages
                if entry.get("isMeta"):
                    continue
                if not initial_prompt:
                    initial_prompt = text.strip()
                    attempt = 1
                else:
                    attempt += 1
                conversation.append(
                    ConversationTurn(
                        role="user",
                        content=text.strip(),
                        attempt_number=attempt,
                    )
                )

        elif msg_type == "assistant":
            content = entry.get("message", {}).get("content", [])
            if isinstance(content, list):
                text_parts = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text_parts.append(block.get("text", ""))

                if text_parts:
                    full_text = "\n".join(text_parts)
                    plan_content = full_text  # Last assistant text = final plan
                    conversation.append(
                        ConversationTurn(
                            role="assistant",
                            content=full_text,
                            attempt_number=attempt if attempt > 0 else 1,
                        )
                    )

    return {
        "conversation": conversation,
        "plan_content": plan_content,
        "initial_prompt": pre_plan_prompt or initial_prompt,
        "num_attempts": max(attempt, 1),
    }
