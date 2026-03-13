import json

from planectra.transcript import extract_plan_conversation, is_in_plan_mode


def _write_transcript(path, entries):
    with open(path, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")


def _make_assistant_tool_use(tool_name):
    return {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [{"type": "tool_use", "name": tool_name, "input": {}}],
        },
    }


def _make_assistant_text(text):
    return {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": text}],
        },
    }


def _make_user(text, is_meta=False):
    entry = {
        "type": "user",
        "message": {"role": "user", "content": text},
    }
    if is_meta:
        entry["isMeta"] = True
    return entry


def test_is_in_plan_mode_true(tmp_path):
    transcript = tmp_path / "transcript.jsonl"
    _write_transcript(transcript, [
        _make_user("help me plan"),
        _make_assistant_tool_use("EnterPlanMode"),
    ])
    assert is_in_plan_mode(str(transcript)) is True


def test_is_in_plan_mode_false_after_exit(tmp_path):
    transcript = tmp_path / "transcript.jsonl"
    _write_transcript(transcript, [
        _make_assistant_tool_use("EnterPlanMode"),
        _make_user("Design a cache"),
        _make_assistant_text("# Plan\nUse Redis"),
        _make_assistant_tool_use("ExitPlanMode"),
    ])
    assert is_in_plan_mode(str(transcript)) is False


def test_is_in_plan_mode_no_plan_events(tmp_path):
    transcript = tmp_path / "transcript.jsonl"
    _write_transcript(transcript, [
        _make_user("hello"),
        _make_assistant_text("Hi there"),
    ])
    assert is_in_plan_mode(str(transcript)) is False


def test_is_in_plan_mode_missing_file():
    assert is_in_plan_mode("/nonexistent/path.jsonl") is False


def test_extract_plan_conversation(tmp_path):
    transcript = tmp_path / "transcript.jsonl"
    _write_transcript(transcript, [
        _make_user("some preamble"),
        _make_assistant_tool_use("EnterPlanMode"),
        _make_user("Design a caching layer"),
        _make_assistant_text("# Plan v1\nBasic cache"),
        _make_user("Add TTL support"),
        _make_assistant_text("# Plan v2\nCache with TTL"),
        _make_assistant_tool_use("ExitPlanMode"),
    ])

    result = extract_plan_conversation(str(transcript))
    assert result["initial_prompt"] == "Design a caching layer"
    assert result["plan_content"] == "# Plan v2\nCache with TTL"
    assert result["num_attempts"] == 2
    assert len(result["conversation"]) == 4  # 2 user + 2 assistant


def test_extract_plan_conversation_no_plan(tmp_path):
    transcript = tmp_path / "transcript.jsonl"
    _write_transcript(transcript, [
        _make_user("hello"),
        _make_assistant_text("hi"),
    ])

    result = extract_plan_conversation(str(transcript))
    assert result["conversation"] == []
    assert result["initial_prompt"] == ""
    assert result["num_attempts"] == 0


def test_extract_skips_meta_messages(tmp_path):
    transcript = tmp_path / "transcript.jsonl"
    _write_transcript(transcript, [
        _make_assistant_tool_use("EnterPlanMode"),
        _make_user("system info", is_meta=True),
        _make_user("Design auth"),
        _make_assistant_text("# Auth Plan"),
        _make_assistant_tool_use("ExitPlanMode"),
    ])

    result = extract_plan_conversation(str(transcript))
    assert result["initial_prompt"] == "Design auth"
    assert result["num_attempts"] == 1
