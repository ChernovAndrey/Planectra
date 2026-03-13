#!/usr/bin/env python3
"""PostToolUse:ExitPlanMode hook — store plan and prompt reflection."""
from __future__ import annotations

import json
import sys

from planectra import config
from planectra.models import PlanRecord
from planectra.session_state import load_session, save_session
from planectra.storage import disk
from planectra.transcript import extract_plan_conversation


def main():
    try:
        hook_input = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    session_id = hook_input.get("session_id", "")
    transcript_path = hook_input.get("transcript_path", "")
    cwd = hook_input.get("cwd", "")

    session = load_session(session_id)

    project = config.get_project_for_dir(cwd)
    if not project:
        sys.exit(0)

    plan_data = extract_plan_conversation(transcript_path)

    if not plan_data["initial_prompt"] and not plan_data["plan_content"]:
        sys.exit(0)

    initial_prompt = session.initial_prompt or plan_data["initial_prompt"]

    record = PlanRecord(
        project_uuid=project.project_uuid,
        project_name=project.project_name,
        initial_prompt=initial_prompt,
        plan_content=plan_data["plan_content"],
        conversation=plan_data["conversation"],
        num_attempts=plan_data["num_attempts"] or session.iteration_count or 1,
        retrieved_plan_uuids=session.retrieved_plan_uuids,
        session_id=session_id,
        metadata={"cwd": cwd},
    )

    disk.save_plan(record)

    # Lazy import: only pay chromadb cost on plan acceptance
    from planectra.storage import vector

    vector.add_plan(
        plan_uuid=record.plan_uuid,
        document=initial_prompt,
        project_uuid=project.project_uuid,
        created_at=record.created_at,
    )

    # Reset session state for next plan
    session.in_plan_mode = False
    session.rag_done = False
    session.initial_prompt = None
    session.iteration_count = 0
    session.retrieved_plan_uuids = []
    save_session(session)

    finalize_msg = (
        f"[Planectra] Plan recorded (UUID: {record.plan_uuid}). "
        "Please call planectra_finalize_plan with your reflection on the planning process."
    )
    if project.include_user_comment:
        finalize_msg += " Ask the user if they'd like to add any feedback."

    print(finalize_msg)


if __name__ == "__main__":
    main()
