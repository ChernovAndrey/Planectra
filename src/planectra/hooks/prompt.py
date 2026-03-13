#!/usr/bin/env python3
"""UserPromptSubmit hook — RAG context injection for plan mode."""
from __future__ import annotations

import json
import sys

from planectra.server.ipc import ipc_request
from planectra.transcript import is_in_plan_mode


def main():
    try:
        hook_input = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    transcript_path = hook_input.get("transcript_path", "")

    # Quick local check: are we in plan mode? (~5ms, no IPC)
    if not transcript_path or not is_in_plan_mode(transcript_path):
        sys.exit(0)

    # In plan mode — query MCP server for RAG context
    response = ipc_request({
        "action": "rag_query",
        "session_id": hook_input.get("session_id", ""),
        "prompt": hook_input.get("prompt", ""),
        "cwd": hook_input.get("cwd", ""),
        "transcript_path": transcript_path,
    })

    context = response.get("context", "")
    if context:
        print(context)


if __name__ == "__main__":
    main()
