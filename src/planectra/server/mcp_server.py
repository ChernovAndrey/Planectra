from __future__ import annotations

import atexit
import os
import sys
from typing import Any

from mcp.server.fastmcp import FastMCP

from planectra import config
from planectra.models import PlanRecord, ProjectConfig, SessionState
from planectra.server import ipc
from planectra.storage import disk, vector
from planectra.transcript import extract_plan_conversation

app = FastMCP("planectra")

# In-memory state
_sessions: dict[str, SessionState] = {}
_global_config_cache: config.GlobalConfig | None = None


def _get_global_config() -> config.GlobalConfig:
    global _global_config_cache
    if _global_config_cache is None:
        config.ensure_dirs()
        _global_config_cache = config.load_global_config()
    return _global_config_cache


def _invalidate_config_cache() -> None:
    global _global_config_cache
    _global_config_cache = None


def _get_session(session_id: str) -> SessionState:
    if session_id not in _sessions:
        _sessions[session_id] = SessionState(session_id)
    return _sessions[session_id]


# ─── MCP Tools ───────────────────────────────────────────────────────────────


@app.tool()
def planectra_init_project(
    project_name: str,
    project_dir: str = "",
    scan_project_ids: list[str] | None = None,
) -> str:
    """Initialize a new project for plan tracking.

    Args:
        project_name: Human-readable name for the project
        project_dir: Working directory for this project (defaults to cwd)
        scan_project_ids: List of project UUIDs to include in RAG search (defaults to self only)
    """
    if not project_dir:
        project_dir = os.getcwd()

    gc = _get_global_config()
    existing_uuid = gc.dir_to_project.get(project_dir)
    if existing_uuid:
        existing = config.load_project_config(existing_uuid)
        if existing:
            return f"Directory already configured as project '{existing.project_name}' ({existing_uuid})"

    proj = ProjectConfig(
        project_name=project_name,
        project_dirs=[project_dir],
        scan_project_ids=scan_project_ids or [],
    )
    if not proj.scan_project_ids:
        proj.scan_project_ids = [proj.project_uuid]

    config.save_project_config(proj)

    gc.dir_to_project[project_dir] = proj.project_uuid
    config.save_global_config(gc)
    _invalidate_config_cache()

    return f"Project '{project_name}' initialized (UUID: {proj.project_uuid})"


@app.tool()
def planectra_list_projects() -> str:
    """List all configured projects."""
    projects = config.list_all_projects()
    if not projects:
        return "No projects configured. Use planectra_init_project to create one."

    lines = []
    for p in projects:
        lines.append(f"- {p.project_name} ({p.project_uuid})")
        for d in p.project_dirs:
            lines.append(f"  dir: {d}")
    return "\n".join(lines)


@app.tool()
def planectra_search_plans(
    query: str,
    project_uuid: str = "",
    top_k: int = 3,
) -> str:
    """Search for similar past plans using semantic search.

    Args:
        query: Search query (natural language)
        project_uuid: Limit search to a specific project (empty = all projects)
        top_k: Number of results to return
    """
    project_uuids = [project_uuid] if project_uuid else None
    results = vector.query_similar(query, project_uuids=project_uuids, top_k=top_k)

    if not results:
        return "No similar plans found."

    lines = []
    for r in results:
        record = disk.load_plan_by_uuid(r["plan_uuid"])
        if record:
            lines.append(f"[{r['similarity']:.0%}] {record.project_name}: {record.initial_prompt[:100]}")
            lines.append(f"  UUID: {r['plan_uuid']}, Attempts: {record.num_attempts}")
        else:
            lines.append(f"[{r['similarity']:.0%}] UUID: {r['plan_uuid']} (record not found on disk)")
    return "\n".join(lines)


@app.tool()
def planectra_finalize_plan(
    plan_uuid: str,
    plan_issues: str = "",
    improvement_summary: str = "",
    rag_usefulness: str = "",
    user_comment: str = "",
) -> str:
    """Finalize a recorded plan with structured reflection data.

    Call this after a plan has been accepted to add your reflection on the planning process.

    Args:
        plan_uuid: UUID of the plan to finalize (provided in the hook message)
        plan_issues: What was wrong/missing in earlier plan drafts
        improvement_summary: What key changes made the final plan better
        rag_usefulness: Was the retrieved RAG context useful? Why/why not?
        user_comment: Optional user feedback on the planning session
    """
    record = disk.load_plan_by_uuid(plan_uuid)
    if not record:
        return f"Plan {plan_uuid} not found."

    record.plan_issues = plan_issues or None
    record.improvement_summary = improvement_summary or None
    record.rag_usefulness = rag_usefulness or None
    record.user_comment = user_comment or None

    disk.update_plan(record)
    return f"Plan {plan_uuid} finalized with reflection data."


@app.tool()
def planectra_update_config(
    project_uuid: str,
    use_rag: bool | None = None,
    top_k: int | None = None,
    include_user_comment: bool | None = None,
    rag_verbosity: str | None = None,
    max_rag_tokens: int | None = None,
    scan_project_ids: list[str] | None = None,
) -> str:
    """Update project configuration.

    Args:
        project_uuid: UUID of the project to update
        use_rag: Enable/disable RAG injection during planning
        top_k: Number of similar plans to retrieve
        include_user_comment: Ask user for feedback after plan acceptance
        rag_verbosity: RAG detail level: "compact", "standard", or "full"
        max_rag_tokens: Maximum tokens for RAG injection
        scan_project_ids: Project UUIDs to include in RAG search
    """
    proj = config.load_project_config(project_uuid)
    if not proj:
        return f"Project {project_uuid} not found."

    if use_rag is not None:
        proj.use_rag = use_rag
    if top_k is not None:
        proj.top_k = top_k
    if include_user_comment is not None:
        proj.include_user_comment = include_user_comment
    if rag_verbosity is not None:
        proj.rag_verbosity = rag_verbosity  # type: ignore[assignment]
    if max_rag_tokens is not None:
        proj.max_rag_tokens = max_rag_tokens
    if scan_project_ids is not None:
        proj.scan_project_ids = scan_project_ids

    config.save_project_config(proj)
    return f"Project {project_uuid} config updated."


# ─── IPC Handler ──────────────────────────────────────────────────────────────


def handle_ipc(request: dict) -> dict:
    """Handle IPC request from hook scripts."""
    action = request.get("action", "")

    handlers = {
        "session_check": _handle_session_check,
        "rag_query": _handle_rag_query,
        "plan_accepted": _handle_plan_accepted,
    }

    handler = handlers.get(action)
    if handler:
        return handler(request)
    return {"status": "error", "message": f"Unknown action: {action}"}


def _handle_session_check(request: dict) -> dict:
    """Check if current directory is configured for plan tracking."""
    cwd = request.get("cwd", "")
    session_id = request.get("session_id", "")

    session = _get_session(session_id)
    session.transcript_path = request.get("transcript_path")

    project = config.get_project_for_dir(cwd)
    if project:
        return {
            "status": "ok",
            "configured": True,
            "project_name": project.project_name,
            "project_uuid": project.project_uuid,
        }
    return {
        "status": "ok",
        "configured": False,
        "message": (
            "[Planectra] This directory is not configured for plan tracking. "
            "Use planectra_init_project to enable it."
        ),
    }


def _handle_rag_query(request: dict) -> dict:
    """Handle RAG query from UserPromptSubmit hook."""
    session_id = request.get("session_id", "")
    prompt = request.get("prompt", "")
    cwd = request.get("cwd", "")

    session = _get_session(session_id)
    session.transcript_path = request.get("transcript_path")

    project = config.get_project_for_dir(cwd)
    if not project or not project.use_rag:
        return {"status": "ok", "context": ""}

    # RAG already done for this plan session — just increment
    if session.rag_done:
        session.iteration_count += 1
        return {"status": "ok", "context": ""}

    # First plan prompt — do RAG
    session.in_plan_mode = True
    session.initial_prompt = prompt
    session.iteration_count = 1
    session.rag_done = True

    scan_ids = project.scan_project_ids or [project.project_uuid]
    results = vector.query_similar(prompt, project_uuids=scan_ids, top_k=project.top_k)

    if not results:
        return {"status": "ok", "context": ""}

    plan_uuids = [r["plan_uuid"] for r in results]
    session.retrieved_plan_uuids = plan_uuids

    context = _format_rag_context(results, project.rag_verbosity, project.max_rag_tokens)
    return {"status": "ok", "context": context}


def _handle_plan_accepted(request: dict) -> dict:
    """Handle plan acceptance notification from PostToolUse hook."""
    session_id = request.get("session_id", "")
    transcript_path = request.get("transcript_path", "")
    cwd = request.get("cwd", "")

    session = _get_session(session_id)

    project = config.get_project_for_dir(cwd)
    if not project:
        return {"status": "error", "message": "No project configured for this directory"}

    plan_data = extract_plan_conversation(transcript_path)

    if not plan_data["initial_prompt"] and not plan_data["plan_content"]:
        return {"status": "error", "message": "Could not extract plan data from transcript"}

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

    finalize_msg = (
        f"[Planectra] Plan recorded (UUID: {record.plan_uuid}). "
        "Please call planectra_finalize_plan with your reflection on the planning process."
    )
    if project.include_user_comment:
        finalize_msg += " Ask the user if they'd like to add any feedback."

    return {
        "status": "ok",
        "message": finalize_msg,
        "plan_uuid": record.plan_uuid,
    }


# ─── RAG Formatting ──────────────────────────────────────────────────────────


def _format_rag_context(
    results: list[dict[str, Any]],
    verbosity: str,
    max_tokens: int,
) -> str:
    """Format RAG results into XML context for injection."""
    parts = ["<planectra-context>"]
    char_budget = max_tokens * 4  # ~4 chars per token
    used = len(parts[0])

    for result in results:
        record = disk.load_plan_by_uuid(result["plan_uuid"])
        if not record:
            continue

        plan_xml = _format_single_plan(record, result["similarity"], verbosity)

        if used + len(plan_xml) > char_budget:
            break

        parts.append(plan_xml)
        used += len(plan_xml)

    parts.append("</planectra-context>")
    return "\n".join(parts)


def _format_single_plan(record: PlanRecord, similarity: float, verbosity: str) -> str:
    """Format a single plan record for RAG context."""
    lines = [
        f'<similar-plan similarity="{similarity:.2f}" '
        f'project="{record.project_name}" '
        f'attempts="{record.num_attempts}" '
        f'date="{record.created_at[:10]}">'
    ]
    lines.append(f"<initial-prompt>{record.initial_prompt}</initial-prompt>")

    if verbosity == "compact":
        if record.plan_issues:
            lines.append(f"<plan-issues>{record.plan_issues}</plan-issues>")
        if record.improvement_summary:
            lines.append(f"<improvement-summary>{record.improvement_summary}</improvement-summary>")

    elif verbosity in ("standard", "full"):
        for turn in record.conversation:
            if turn.role == "assistant" and turn.attempt_number:
                attempt = turn.attempt_number
                is_final = attempt == record.num_attempts
                status = "accepted" if is_final else "rejected"
                lines.append(f'<draft attempt="{attempt}" status="{status}">')

                content = turn.content
                if verbosity == "standard" and len(content) > 2000:
                    content = content[:2000] + "\n[...truncated...]"
                lines.append(content)
                lines.append("</draft>")

            elif turn.role == "user" and turn.attempt_number and turn.attempt_number > 1:
                lines.append(
                    f'<user-feedback attempt="{turn.attempt_number - 1}">'
                    f"{turn.content}</user-feedback>"
                )

        if record.plan_issues:
            lines.append(f"<plan-issues>{record.plan_issues}</plan-issues>")
        if record.improvement_summary:
            lines.append(f"<improvement-summary>{record.improvement_summary}</improvement-summary>")
        if record.rag_usefulness:
            lines.append(f"<rag-usefulness>{record.rag_usefulness}</rag-usefulness>")

    lines.append("</similar-plan>")
    return "\n".join(lines)


# ─── Main ─────────────────────────────────────────────────────────────────────


def main():
    """Start the MCP server with IPC socket."""
    config.ensure_dirs()

    # Start IPC socket server in background thread
    ipc_thread = ipc.start_ipc_server(handle_ipc)
    if ipc_thread is None:
        print("[Planectra] Warning: Could not start IPC server (socket in use?)", file=sys.stderr)

    atexit.register(ipc.cleanup_socket)

    # Run MCP server (blocks on stdio)
    app.run(transport="stdio")


if __name__ == "__main__":
    main()
