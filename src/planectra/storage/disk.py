from __future__ import annotations

import json
from pathlib import Path

from planectra import config
from planectra.models import PlanRecord


def get_plan_path(project_uuid: str, plan_uuid: str) -> Path:
    return config.PROJECTS_DIR / project_uuid / "plans" / f"{plan_uuid}.json"


def save_plan(record: PlanRecord) -> Path:
    path = get_plan_path(record.project_uuid, record.plan_uuid)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record.model_dump(), indent=2))
    return path


def load_plan(project_uuid: str, plan_uuid: str) -> PlanRecord | None:
    path = get_plan_path(project_uuid, plan_uuid)
    if path.exists():
        return PlanRecord(**json.loads(path.read_text()))
    return None


def load_plan_by_uuid(plan_uuid: str) -> PlanRecord | None:
    """Search across all projects for a plan by UUID."""
    projects_dir = config.PROJECTS_DIR
    if not projects_dir.exists():
        return None
    for project_dir in projects_dir.iterdir():
        if project_dir.is_dir():
            plan_path = project_dir / "plans" / f"{plan_uuid}.json"
            if plan_path.exists():
                return PlanRecord(**json.loads(plan_path.read_text()))
    return None


def list_plans(project_uuid: str) -> list[PlanRecord]:
    plans_dir = config.PROJECTS_DIR / project_uuid / "plans"
    if not plans_dir.exists():
        return []
    records = []
    for f in plans_dir.glob("*.json"):
        records.append(PlanRecord(**json.loads(f.read_text())))
    return records


def list_recent_plans(project_uuid: str = "", top_k: int = 5) -> list[PlanRecord]:
    """List recent plans sorted by created_at descending.

    If project_uuid is provided, only list plans from that project.
    Otherwise, iterate all project dirs under PROJECTS_DIR.
    """
    records: list[PlanRecord] = []
    projects_dir = config.PROJECTS_DIR
    if not projects_dir.exists():
        return []

    if project_uuid:
        dirs = [projects_dir / project_uuid]
    else:
        dirs = [d for d in projects_dir.iterdir() if d.is_dir()]

    for project_dir in dirs:
        plans_dir = project_dir / "plans"
        if not plans_dir.exists():
            continue
        for f in plans_dir.glob("*.json"):
            records.append(PlanRecord(**json.loads(f.read_text())))

    records.sort(key=lambda r: r.created_at, reverse=True)
    return records[:top_k]


def update_plan(record: PlanRecord) -> Path:
    return save_plan(record)
