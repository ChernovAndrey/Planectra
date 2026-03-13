#!/usr/bin/env python3
"""SessionStart hook — project detection and notification."""
from __future__ import annotations

import json
import sys

from planectra import config
from planectra.session_state import cleanup_stale_sessions


def main():
    try:
        hook_input = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    cwd = hook_input.get("cwd", "")

    project = config.get_project_for_dir(cwd)
    if project:
        print(f"[Planectra] Project: {project.project_name}")
    else:
        existing_projects = config.list_all_projects()
        project_list = [p.project_name for p in existing_projects]

        if project_list:
            names = ", ".join(project_list)
            print(
                f"[Planectra] This directory is not configured for plan tracking.\n"
                f"Existing projects: {names}\n"
                f"Use planectra_init_project to create a new project or assign this directory to an existing one."
            )
        else:
            print(
                "[Planectra] This directory is not configured for plan tracking. "
                "Use planectra_init_project to enable it."
            )

    # Opportunistic cleanup of stale session files
    cleanup_stale_sessions()


if __name__ == "__main__":
    main()
