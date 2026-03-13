from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

from planectra.models import PlanRecord
from planectra.storage import disk, vector

PLANECTRA_NAMESPACE = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")
PLANS_DIR = Path.home() / ".claude" / "plans"


def import_existing_plans(project_uuid: str | None = None, project_name: str = "imported") -> str:
    """Import existing plans from ~/.claude/plans/*.md."""
    if not PLANS_DIR.exists():
        return "No plans directory found at ~/.claude/plans/"

    plan_files = sorted(PLANS_DIR.glob("*.md"))
    if not plan_files:
        return "No .md files found in ~/.claude/plans/"

    imported = 0
    skipped = 0
    errors = 0

    for plan_file in plan_files:
        try:
            slug = plan_file.stem
            plan_uuid = str(uuid.uuid5(PLANECTRA_NAMESPACE, slug))

            if vector.plan_exists(plan_uuid):
                skipped += 1
                continue

            content = plan_file.read_text()
            mtime = datetime.fromtimestamp(plan_file.stat().st_mtime, tz=UTC)

            embed_text = _extract_embed_text(content)
            title = _extract_title(content, slug)

            proj_uuid = project_uuid or "imported"

            record = PlanRecord(
                plan_uuid=plan_uuid,
                project_uuid=proj_uuid,
                project_name=project_name,
                initial_prompt=title,
                plan_content=content,
                created_at=mtime.isoformat(),
                metadata={"source": "import", "slug": slug},
            )

            disk.save_plan(record)
            vector.add_plan(
                plan_uuid=plan_uuid,
                document=embed_text,
                project_uuid=proj_uuid,
                created_at=record.created_at,
            )
            imported += 1

        except Exception:
            errors += 1

    total = imported + skipped + errors
    return f"Imported {imported}/{total} plans ({skipped} already imported, {errors} errors)"


def _extract_embed_text(content: str) -> str:
    """Extract text to embed from plan content.

    Prefers ## Context section, falls back to first 500 chars.
    """
    context_match = re.search(r"## Context\s*\n(.*?)(?=\n## |\Z)", content, re.DOTALL)
    if context_match:
        return context_match.group(1).strip()[:1000]
    return content[:500]


def _extract_title(content: str, fallback_slug: str) -> str:
    """Extract title from plan content."""
    match = re.search(r"^#\s+(?:Plan:\s*)?(.+)$", content, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return fallback_slug.replace("-", " ").title()
