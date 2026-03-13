#!/usr/bin/env python3
"""SessionStart hook — project detection and notification."""
from __future__ import annotations

import json
import sys

from planectra.server.ipc import ipc_request


def main():
    try:
        hook_input = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    response = ipc_request({
        "action": "session_check",
        "session_id": hook_input.get("session_id", ""),
        "cwd": hook_input.get("cwd", ""),
        "transcript_path": hook_input.get("transcript_path", ""),
    })

    if response.get("status") == "ok":
        if response.get("configured"):
            print(f"[Planectra] Project: {response.get('project_name')}")
        else:
            print(response.get("message", "[Planectra] Directory not configured."))


if __name__ == "__main__":
    main()
