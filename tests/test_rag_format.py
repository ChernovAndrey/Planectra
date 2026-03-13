from unittest.mock import patch

from planectra.models import ConversationTurn, PlanRecord
from planectra.rag_format import format_rag_context, format_single_plan


def _make_record(**kwargs):
    defaults = {
        "project_uuid": "proj-1",
        "project_name": "test-project",
        "initial_prompt": "Design an auth system",
        "plan_content": "# Auth Plan\nUse JWT tokens",
        "num_attempts": 2,
        "created_at": "2026-03-10T14:30:00+00:00",
    }
    defaults.update(kwargs)
    return PlanRecord(**defaults)


def test_format_single_plan_compact():
    record = _make_record(
        plan_issues="Missing rate limiting",
        improvement_summary="Added rate limiting middleware",
    )
    result = format_single_plan(record, similarity=0.85, verbosity="compact")

    assert 'similarity="0.85"' in result
    assert 'project="test-project"' in result
    assert 'attempts="2"' in result
    assert "<initial-prompt>Design an auth system</initial-prompt>" in result
    assert "<plan-issues>Missing rate limiting</plan-issues>" in result
    assert "<improvement-summary>Added rate limiting middleware</improvement-summary>" in result
    # compact should NOT include drafts
    assert "<draft" not in result


def test_format_single_plan_standard():
    record = _make_record(
        conversation=[
            ConversationTurn(role="assistant", content="Plan v1: basic JWT", attempt_number=1),
            ConversationTurn(role="user", content="Add refresh tokens", attempt_number=2),
            ConversationTurn(role="assistant", content="Plan v2: JWT + refresh", attempt_number=2),
        ],
        plan_issues="Missing refresh tokens",
    )
    result = format_single_plan(record, similarity=0.75, verbosity="standard")

    assert '<draft attempt="1" status="rejected">' in result
    assert '<draft attempt="2" status="accepted">' in result
    assert '<user-feedback attempt="1">' in result
    assert "<plan-issues>Missing refresh tokens</plan-issues>" in result


def test_format_single_plan_standard_truncates():
    long_content = "x" * 3000
    record = _make_record(
        conversation=[
            ConversationTurn(role="assistant", content=long_content, attempt_number=1),
        ],
        num_attempts=1,
    )
    result = format_single_plan(record, similarity=0.9, verbosity="standard")
    assert "[...truncated...]" in result


def test_format_single_plan_full_no_truncation():
    long_content = "x" * 3000
    record = _make_record(
        conversation=[
            ConversationTurn(role="assistant", content=long_content, attempt_number=1),
        ],
        num_attempts=1,
    )
    result = format_single_plan(record, similarity=0.9, verbosity="full")
    assert "[...truncated...]" not in result
    assert long_content in result


def test_format_rag_context_respects_token_budget():
    records = {}
    for i in range(5):
        uuid = f"plan-{i}"
        records[uuid] = _make_record(
            plan_uuid=uuid,
            initial_prompt=f"Prompt {i}",
            plan_content="x" * 500,
        )

    results = [
        {"plan_uuid": f"plan-{i}", "similarity": 0.9 - i * 0.1}
        for i in range(5)
    ]

    with patch("planectra.rag_format.disk.load_plan_by_uuid", side_effect=lambda uuid: records.get(uuid)):
        # Very small budget — should limit plans included
        context = format_rag_context(results, verbosity="compact", max_tokens=100)

    assert "<planectra-context>" in context
    assert "</planectra-context>" in context


def test_format_rag_context_empty_results():
    context = format_rag_context([], verbosity="standard", max_tokens=4000)
    assert context == "<planectra-context>\n</planectra-context>"


def test_format_rag_context_missing_record():
    results = [{"plan_uuid": "nonexistent", "similarity": 0.9}]

    with patch("planectra.rag_format.disk.load_plan_by_uuid", return_value=None):
        context = format_rag_context(results, verbosity="standard", max_tokens=4000)

    assert context == "<planectra-context>\n</planectra-context>"
