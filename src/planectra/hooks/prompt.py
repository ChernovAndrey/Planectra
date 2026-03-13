#!/usr/bin/env python3
"""UserPromptSubmit hook — RAG context injection for plan mode."""
from __future__ import annotations

import json
import sys

from planectra import config
from planectra.session_state import load_session, save_session
from planectra.transcript import is_in_plan_mode


def main():
    try:
        hook_input = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    transcript_path = hook_input.get("transcript_path", "")

    # Quick local check: are we in plan mode? (~5ms)
    if not transcript_path or not is_in_plan_mode(transcript_path):
        sys.exit(0)

    session_id = hook_input.get("session_id", "")
    session = load_session(session_id)
    session.transcript_path = transcript_path

    # RAG already done for this plan session — just increment
    if session.rag_done:
        session.iteration_count += 1
        save_session(session)
        sys.exit(0)

    # First plan prompt — check project config
    cwd = hook_input.get("cwd", "")
    project = config.get_project_for_dir(cwd)
    if not project or not project.use_rag:
        sys.exit(0)

    prompt = hook_input.get("prompt", "")

    session.in_plan_mode = True
    session.initial_prompt = prompt
    session.iteration_count = 1
    session.rag_done = True

    # Lazy import: only pay chromadb cost on first plan prompt
    from planectra.rag_format import format_rag_context
    from planectra.storage import vector

    gc = config.load_global_config()
    scan_ids = None if gc.default_scan_all_projects else project.scan_project_ids or [project.project_uuid]
    results = vector.query_similar(prompt, project_uuids=scan_ids, top_k=project.top_k)

    if results:
        plan_uuids = [r["plan_uuid"] for r in results]
        session.retrieved_plan_uuids = plan_uuids
        context = format_rag_context(results, project.rag_verbosity, project.max_rag_tokens)
        print(context)

    save_session(session)


if __name__ == "__main__":
    main()
