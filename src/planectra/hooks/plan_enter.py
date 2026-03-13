#!/usr/bin/env python3
"""PostToolUse:EnterPlanMode hook — set session state and inject RAG context."""
from __future__ import annotations

import json
import sys

from planectra import config
from planectra.session_state import load_session, save_session
from planectra.transcript import extract_initial_prompt


def main():
    try:
        hook_input = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    session_id = hook_input.get("session_id", "")
    transcript_path = hook_input.get("transcript_path", "")

    session = load_session(session_id)
    session.in_plan_mode = True
    session.transcript_path = transcript_path

    # Extract initial prompt from transcript (last user message before EnterPlanMode)
    initial_prompt = extract_initial_prompt(transcript_path) if transcript_path else ""

    session.initial_prompt = initial_prompt
    session.iteration_count = 1
    session.rag_done = True
    save_session(session)  # persist before slow RAG

    # RAG injection — depends on project config
    cwd = hook_input.get("cwd", "")
    project = config.get_project_for_dir(cwd)
    if not project or not project.use_rag or not initial_prompt:
        sys.exit(0)

    # Lazy import: only pay chromadb cost when entering plan mode
    from planectra.rag_format import format_rag_context
    from planectra.storage import vector

    gc = config.load_global_config()
    scan_ids = None if gc.default_scan_all_projects else project.scan_project_ids or [project.project_uuid]
    results = vector.query_similar(initial_prompt, project_uuids=scan_ids, top_k=project.top_k)

    if results:
        plan_uuids = [r["plan_uuid"] for r in results]
        session.retrieved_plan_uuids = plan_uuids
        context = format_rag_context(results, project.rag_verbosity, project.max_rag_tokens)
        print(context)

    save_session(session)


if __name__ == "__main__":
    main()
