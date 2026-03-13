#!/usr/bin/env python3
"""UserPromptSubmit hook — detect plan mode and inject RAG context on first prompt."""
from __future__ import annotations

import json
import sys

from planectra import config
from planectra.session_state import load_session, save_session


def main():
    try:
        hook_input = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    permission_mode = hook_input.get("permission_mode", "")
    if permission_mode != "plan":
        sys.exit(0)

    session_id = hook_input.get("session_id", "")
    session = load_session(session_id)
    session.transcript_path = hook_input.get("transcript_path", "")

    if not session.rag_done:
        # First prompt in plan mode — inject RAG
        prompt = hook_input.get("prompt", "")
        cwd = hook_input.get("cwd", "")
        session.initial_prompt = prompt
        session.in_plan_mode = True
        session.rag_done = True
        session.iteration_count = 1
        save_session(session)  # persist before slow RAG

        project = config.get_project_for_dir(cwd)
        if project and project.use_rag and prompt:
            # Lazy imports
            from planectra.rag_format import format_rag_context
            from planectra.storage import vector

            gc = config.load_global_config()
            scan_ids = None if gc.default_scan_all_projects else project.scan_project_ids or [project.project_uuid]
            results = vector.query_similar(prompt, project_uuids=scan_ids, top_k=project.top_k)

            if results:
                session.retrieved_plan_uuids = [r["plan_uuid"] for r in results]
                save_session(session)
                context = format_rag_context(results, project.rag_verbosity, project.max_rag_tokens)
                print(context)  # stdout → injected as additionalContext
    else:
        # Subsequent prompts — increment iteration
        session.iteration_count += 1
        save_session(session)

    sys.exit(0)


if __name__ == "__main__":
    main()
