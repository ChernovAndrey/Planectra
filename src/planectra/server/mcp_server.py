from __future__ import annotations

import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from planectra import config
from planectra.storage import disk, vector

app = FastMCP("planectra")

# Config cache (within MCP process)
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


# ─── MCP Tools ───────────────────────────────────────────────────────────────


@app.tool()
def planectra_init_project(
    project_name: str,
    project_dir: str = "",
    existing_project_uuid: str = "",
    scan_project_ids: list[str] | None = None,
) -> str:
    """Initialize a new project or assign this directory to an existing project.

    Args:
        project_name: Human-readable name for the project (ignored if existing_project_uuid is set)
        project_dir: Working directory for this project (defaults to cwd)
        existing_project_uuid: UUID of an existing project to assign this directory to (skip creation)
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

    # Assign to existing project
    if existing_project_uuid:
        proj = config.load_project_config(existing_project_uuid)
        if not proj:
            return f"Project {existing_project_uuid} not found."
        if project_dir not in proj.project_dirs:
            proj.project_dirs.append(project_dir)
            config.save_project_config(proj)
        gc.dir_to_project[project_dir] = proj.project_uuid
        config.save_global_config(gc)
        _invalidate_config_cache()
        return f"Directory assigned to existing project '{proj.project_name}' ({proj.project_uuid})"

    # Create new project
    proj = config.create_project_config(project_name, project_dirs=[project_dir])
    if scan_project_ids:
        proj.scan_project_ids = scan_project_ids

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


# ─── Main ─────────────────────────────────────────────────────────────────────


def main():
    """Start the MCP server."""
    config.ensure_dirs()
    app.run(transport="stdio")


if __name__ == "__main__":
    main()
