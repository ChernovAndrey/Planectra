from __future__ import annotations

import click

from planectra import __version__


@click.group()
@click.version_option(version=__version__)
def main():
    """Planectra - Planning conversation tracker with RAG for Claude Code."""


@main.command()
@click.option(
    "--scope",
    type=click.Choice(["global", "project"]),
    default="global",
    help="global: ~/.claude/ (all projects). project: .claude/ in cwd (this project only).",
)
def install(scope: str):
    """Install Planectra hooks and MCP server."""
    from pathlib import Path

    from planectra import config
    from planectra.installer import install as do_install

    click.echo(do_install(scope=scope))
    click.echo("\nPlanectra installed successfully!")

    # Auto-initialize project when scope=project
    if scope == "project":
        import os

        cwd = os.getcwd()
        gc = config.load_global_config()
        if cwd not in gc.dir_to_project:
            dir_name = os.path.basename(cwd)
            project_name = click.prompt("Project name for this directory", default=dir_name)
            proj = config.create_project_config(project_name, project_dirs=[cwd])
            config.save_project_config(proj)
            gc.dir_to_project[cwd] = proj.project_uuid
            config.save_global_config(gc)
            click.echo(f"Project '{project_name}' initialized ({proj.project_uuid})")

    # Interactive configuration of global defaults
    click.echo("\n--- Default settings (inherited by new projects) ---")
    click.echo("Press Enter to accept defaults.\n")

    gc = config.load_global_config()
    gc.default_use_rag = click.confirm("Enable RAG context injection?", default=gc.default_use_rag)
    gc.default_top_k = click.prompt("Number of similar plans to retrieve (top_k)", default=gc.default_top_k, type=int)
    gc.default_rag_verbosity = click.prompt(
        "RAG verbosity (compact/standard/full)", default=gc.default_rag_verbosity,
        type=click.Choice(["compact", "standard", "full"]),
    )
    gc.default_max_rag_tokens = click.prompt("Max RAG tokens", default=gc.default_max_rag_tokens, type=int)
    gc.default_include_user_comment = click.confirm(
        "Ask user for feedback after plan acceptance?", default=gc.default_include_user_comment,
    )
    gc.default_scan_all_projects = click.confirm(
        "Search across all Planectra projects for RAG? (no = current project only)",
        default=gc.default_scan_all_projects,
    )
    config.save_global_config(gc)
    click.echo("Settings saved.")

    # Check for existing plans and offer to import
    plans_dir = Path.home() / ".claude" / "plans"
    if plans_dir.exists():
        plan_files = list(plans_dir.glob("*.md"))
        if plan_files and click.confirm(
            f"\nFound {len(plan_files)} existing plan(s) in ~/.claude/plans/. Import them now?"
        ):
            from planectra.importer import import_existing_plans

            click.echo(import_existing_plans())


@main.command()
@click.option(
    "--scope",
    type=click.Choice(["global", "project"]),
    default="global",
    help="global: ~/.claude/ (all projects). project: .claude/ in cwd (this project only).",
)
def uninstall(scope: str):
    """Remove Planectra hooks and MCP server."""
    from planectra.installer import uninstall as do_uninstall

    click.echo(do_uninstall(scope=scope))


@main.command()
@click.argument("project_name")
@click.option("--dir", "project_dir", default="", help="Project directory (default: cwd)")
def init(project_name: str, project_dir: str):
    """Initialize a new project for plan tracking."""
    import os

    from planectra import config

    if not project_dir:
        project_dir = os.getcwd()

    gc = config.load_global_config()
    existing = gc.dir_to_project.get(project_dir)
    if existing:
        proj = config.load_project_config(existing)
        if proj:
            click.echo(f"Directory already configured as '{proj.project_name}' ({existing})")
            return

    proj = config.create_project_config(project_name, project_dirs=[project_dir])
    config.save_project_config(proj)

    gc.dir_to_project[project_dir] = proj.project_uuid
    config.save_global_config(gc)
    click.echo(f"Project '{project_name}' initialized (UUID: {proj.project_uuid})")


@main.command()
def projects():
    """List all configured projects."""
    from planectra.config import list_all_projects

    projs = list_all_projects()
    if not projs:
        click.echo("No projects configured.")
        return

    for p in projs:
        click.echo(f"  {p.project_name} ({p.project_uuid})")
        for d in p.project_dirs:
            click.echo(f"    dir: {d}")


@main.command()
@click.argument("query")
@click.option("--project", "project_uuid", default="", help="Limit to project UUID")
@click.option("--top-k", default=3, help="Number of results")
def search(query: str, project_uuid: str, top_k: int):
    """Search for similar past plans."""
    from planectra.storage import disk, vector

    project_uuids = [project_uuid] if project_uuid else None
    results = vector.query_similar(query, project_uuids=project_uuids, top_k=top_k)
    if not results:
        click.echo("No similar plans found.")
        return

    for r in results:
        record = disk.load_plan_by_uuid(r["plan_uuid"])
        if record:
            click.echo(f"[{r['similarity']:.0%}] {record.project_name}: {record.initial_prompt[:100]}")
            click.echo(f"     UUID: {r['plan_uuid']}, Attempts: {record.num_attempts}")


def _format_date(iso_str: str) -> str:
    """Parse ISO date string to human-friendly format."""
    from datetime import datetime

    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.strftime("%b %d, %Y at %I:%M %p")
    except (ValueError, TypeError):
        return iso_str or "unknown"


def _section(title: str, width: int = 40) -> str:
    """Return a styled section header like: ── Title ──────────────"""
    prefix = f"\u2500\u2500 {title} "
    return prefix + "\u2500" * max(0, width - len(prefix))


@main.command()
@click.argument("plan_uuid")
@click.option("--json", "as_json", is_flag=True, help="Output as raw JSON")
def show(plan_uuid: str, as_json: bool):
    """Show full details of a plan by UUID."""
    import json as json_module

    from planectra.storage.disk import load_plan_by_uuid

    record = load_plan_by_uuid(plan_uuid)
    if not record:
        click.echo(f"Plan {plan_uuid} not found.")
        return

    if as_json:
        click.echo(json_module.dumps(record.model_dump(), indent=2))
        return

    short_id = record.plan_uuid[:8]
    click.echo(f"Plan {short_id}")
    click.echo(f"Project:  {record.project_name}")
    click.echo(f"Created:  {_format_date(record.created_at)}")
    click.echo(f"Attempts: {record.num_attempts}")
    click.echo(f"Full UUID: {record.plan_uuid}")

    # Prompt
    click.echo(f"\n{_section('Prompt')}")
    if record.initial_prompt:
        click.echo(f"  {record.initial_prompt}")
    else:
        click.echo(click.style("  (no prompt captured)", dim=True))

    # Conversation
    if record.conversation:
        click.echo(f"\n{_section(f'Conversation ({len(record.conversation)} turns)')}")
        for turn in record.conversation:
            role = "You" if turn.role == "user" else "Claude"
            attempt = f" [attempt {turn.attempt_number}]" if turn.attempt_number else ""
            click.echo(f"\n  {click.style(role, bold=True)}{attempt}:")
            content = turn.content[:500] + ("..." if len(turn.content) > 500 else "")
            for line in content.split("\n"):
                click.echo(f"  {line}")

    # Plan
    click.echo(f"\n{_section('Plan')}")
    if record.plan_content:
        content = record.plan_content[:2000]
        for line in content.split("\n"):
            click.echo(f"  {line}")
        if len(record.plan_content) > 2000:
            msg = f"  ... ({len(record.plan_content)} chars total, use --json for full content)"
            click.echo(click.style(msg, dim=True))
    else:
        click.echo(click.style("  (no plan content)", dim=True))

    # Reflection
    if record.plan_issues or record.improvement_summary or record.rag_usefulness or record.user_comment:
        click.echo(f"\n{_section('Reflection')}")
        if record.plan_issues:
            click.echo(f"  Issues:       {record.plan_issues}")
        if record.improvement_summary:
            click.echo(f"  Improvements: {record.improvement_summary}")
        if record.rag_usefulness:
            click.echo(f"  RAG useful:   {record.rag_usefulness}")
        if record.user_comment:
            click.echo(f"  User comment: {record.user_comment}")


@main.command()
@click.option("--project", "project_uuid", default="", help="Limit to project UUID")
@click.option("--top-k", default=5, help="Number of recent plans to show")
def recent(project_uuid: str, top_k: int):
    """Show the most recent plans."""
    from planectra.storage.disk import list_recent_plans

    results = list_recent_plans(project_uuid=project_uuid, top_k=top_k)
    if not results:
        click.echo("No plans found.")
        return

    for record in results:
        click.echo(f"[{_format_date(record.created_at)}] {record.project_name}: {record.initial_prompt[:100]}")
        click.echo(f"     UUID: {record.plan_uuid}, Attempts: {record.num_attempts}")


@main.command("import")
@click.option("--project", "project_uuid", default=None, help="Assign to project UUID")
@click.option("--name", "project_name", default="imported", help="Project name for imported plans")
def import_plans(project_uuid: str | None, project_name: str):
    """Import existing plans from ~/.claude/plans/."""
    from planectra.importer import import_existing_plans

    click.echo(import_existing_plans(project_uuid, project_name))


@main.command("config")
@click.argument("project_uuid")
@click.option("--use-rag/--no-rag", default=None, help="Enable/disable RAG")
@click.option("--top-k", default=None, type=int, help="Number of RAG results")
@click.option("--verbosity", default=None, type=click.Choice(["compact", "standard", "full"]))
@click.option("--max-tokens", default=None, type=int, help="Max RAG tokens")
def config_cmd(
    project_uuid: str, use_rag: bool | None, top_k: int | None, verbosity: str | None, max_tokens: int | None
):
    """View or update project configuration."""
    from planectra import config as cfg

    proj = cfg.load_project_config(project_uuid)
    if not proj:
        click.echo(f"Project {project_uuid} not found.")
        return

    changed = False
    if use_rag is not None:
        proj.use_rag = use_rag
        changed = True
    if top_k is not None:
        proj.top_k = top_k
        changed = True
    if verbosity is not None:
        proj.rag_verbosity = verbosity  # type: ignore[assignment]
        changed = True
    if max_tokens is not None:
        proj.max_rag_tokens = max_tokens
        changed = True

    if changed:
        cfg.save_project_config(proj)
        click.echo(f"Project {project_uuid} config updated.")
    else:
        click.echo(f"Project: {proj.project_name}")
        click.echo(f"  use_rag: {proj.use_rag}")
        click.echo(f"  top_k: {proj.top_k}")
        click.echo(f"  verbosity: {proj.rag_verbosity}")
        click.echo(f"  max_rag_tokens: {proj.max_rag_tokens}")
        click.echo(f"  include_user_comment: {proj.include_user_comment}")


@main.command()
def export():
    """Export all plans as JSON."""
    import json as json_module

    from planectra.config import list_all_projects
    from planectra.storage.disk import list_plans

    all_plans = []
    for proj in list_all_projects():
        for plan in list_plans(proj.project_uuid):
            all_plans.append(plan.model_dump())

    click.echo(json_module.dumps(all_plans, indent=2))
