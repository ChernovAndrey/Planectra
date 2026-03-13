"""RAG context formatting for plan injection."""
from __future__ import annotations

from typing import Any

from planectra.models import PlanRecord
from planectra.storage import disk


def format_rag_context(
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

        plan_xml = format_single_plan(record, result["similarity"], verbosity)

        if used + len(plan_xml) > char_budget:
            break

        parts.append(plan_xml)
        used += len(plan_xml)

    parts.append("</planectra-context>")
    return "\n".join(parts)


def format_single_plan(record: PlanRecord, similarity: float, verbosity: str) -> str:
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
