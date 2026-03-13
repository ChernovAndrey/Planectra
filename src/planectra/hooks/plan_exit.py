#!/usr/bin/env python3
"""PostToolUse:ExitPlanMode hook — store plan and prompt reflection."""
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
        "action": "plan_accepted",
        "session_id": hook_input.get("session_id", ""),
        "transcript_path": hook_input.get("transcript_path", ""),
        "cwd": hook_input.get("cwd", ""),
    })

    message = response.get("message", "")
    if message:
        print(message)


if __name__ == "__main__":
    main()
