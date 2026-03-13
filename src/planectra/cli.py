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
    from planectra.installer import install as do_install

    click.echo(do_install(scope=scope))
    click.echo("\nPlanectra installed successfully!")


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
    from planectra.models import ProjectConfig

    if not project_dir:
        project_dir = os.getcwd()

    gc = config.load_global_config()
    existing = gc.dir_to_project.get(project_dir)
    if existing:
        proj = config.load_project_config(existing)
        if proj:
            click.echo(f"Directory already configured as '{proj.project_name}' ({existing})")
            return

    proj = ProjectConfig(
        project_name=project_name,
        project_dirs=[project_dir],
        scan_project_ids=[],
    )
    proj.scan_project_ids = [proj.project_uuid]
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
