#!/usr/bin/env python3
"""SessionStart hook — project detection and notification."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from planectra import config
from planectra.session_state import cleanup_stale_sessions


def _suggest_project_name(cwd: str) -> str:
    """Derive a suggested project name from the cwd directory name."""
    if not cwd or cwd == "/":
        return "my-project"
    name = Path(cwd).name
    return name if name else "my-project"


def main():
    try:
        hook_input = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    cwd = hook_input.get("cwd", "")

    project = config.get_project_for_dir(cwd)
    if project:
        output = {
            "systemMessage": (
                f"[Planectra] Project: {project.project_name}"
            ),
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": (
                    f"[Planectra] Project: {project.project_name}\n"
                    f"Inform the user that this session is using"
                    f" Planectra plan tracking for project"
                    f' "{project.project_name}".'
                ),
            },
        }
        print(json.dumps(output))
    else:
        suggested_name = _suggest_project_name(cwd)
        existing_projects = config.list_all_projects()

        context_lines = [
            "[Planectra] This directory is not configured"
            " for plan tracking.",
            "IMPORTANT: Before addressing the user's request,"
            " ask them if they'd like to enable Planectra"
            " plan tracking for this directory.",
            f'Suggested project_name: "{suggested_name}"',
            f'Suggested project_dir: "{cwd}"',
        ]

        if existing_projects:
            context_lines.append(
                "Existing projects"
                " (user can assign this directory to one):"
            )
            for p in existing_projects:
                context_lines.append(
                    f"  - {p.project_name}"
                    f" (UUID: {p.project_uuid})"
                )

        context_lines.append(
            "If the user declines, proceed normally."
            " Do not ask again in this session."
        )

        output = {
            "systemMessage": (
                "[Planectra] No project configured"
            ),
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": "\n".join(context_lines),
            },
        }
        print(json.dumps(output))

    # Opportunistic cleanup of stale session files
    cleanup_stale_sessions()


if __name__ == "__main__":
    main()
