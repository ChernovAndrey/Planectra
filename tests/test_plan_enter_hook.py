import json
from unittest.mock import MagicMock, patch

from planectra.hooks.plan_enter import main
from planectra.hooks.prompt import main as prompt_main
from planectra.models import ProjectConfig, GlobalConfig, SessionState
from planectra.transcript import extract_initial_prompt


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


def _make_user(text, is_meta=False):
    entry = {
        "type": "user",
        "message": {"role": "user", "content": text},
    }
    if is_meta:
        entry["isMeta"] = True
    return entry


def _make_assistant_text(text):
    return {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": text}],
        },
    }


# --- extract_initial_prompt tests ---

def test_extract_initial_prompt_basic(tmp_path):
    transcript = tmp_path / "transcript.jsonl"
    _write_transcript(transcript, [
        _make_user("Design a caching layer"),
        _make_assistant_tool_use("EnterPlanMode"),
    ])
    assert extract_initial_prompt(str(transcript)) == "Design a caching layer"


def test_extract_initial_prompt_skips_meta(tmp_path):
    transcript = tmp_path / "transcript.jsonl"
    _write_transcript(transcript, [
        _make_user("Design auth"),
        _make_user("system info", is_meta=True),
        _make_assistant_tool_use("EnterPlanMode"),
    ])
    assert extract_initial_prompt(str(transcript)) == "Design auth"


def test_extract_initial_prompt_missing_file():
    assert extract_initial_prompt("/nonexistent/path.jsonl") == ""


def test_extract_initial_prompt_no_enter_plan(tmp_path):
    transcript = tmp_path / "transcript.jsonl"
    _write_transcript(transcript, [
        _make_user("hello"),
        _make_assistant_text("hi"),
    ])
    assert extract_initial_prompt(str(transcript)) == ""


def test_extract_initial_prompt_uses_last_enter(tmp_path):
    """When there are multiple EnterPlanMode events, use the last one."""
    transcript = tmp_path / "transcript.jsonl"
    _write_transcript(transcript, [
        _make_user("first plan"),
        _make_assistant_tool_use("EnterPlanMode"),
        _make_assistant_tool_use("ExitPlanMode"),
        _make_user("second plan"),
        _make_assistant_tool_use("EnterPlanMode"),
    ])
    assert extract_initial_prompt(str(transcript)) == "second plan"


# --- plan_enter hook tests ---

def _run_hook(hook_input):
    """Run the plan_enter hook with the given input dict."""
    with patch("sys.stdin", MagicMock(read=lambda: json.dumps(hook_input))):
        with patch("json.load", return_value=hook_input):
            main()


def test_hook_sets_session_state(tmp_path, monkeypatch):
    transcript = tmp_path / "transcript.jsonl"
    _write_transcript(transcript, [
        _make_user("Build an API"),
        _make_assistant_tool_use("EnterPlanMode"),
    ])

    saved_sessions = []
    session = SessionState(session_id="test-session")

    hook_input = {
        "session_id": "test-session",
        "transcript_path": str(transcript),
        "cwd": "/some/dir",
    }

    with patch("planectra.hooks.plan_enter.load_session", return_value=session), \
         patch("planectra.hooks.plan_enter.save_session", side_effect=saved_sessions.append), \
         patch("planectra.hooks.plan_enter.config.get_project_for_dir", return_value=None), \
         patch("json.load", return_value=hook_input), \
         patch("sys.stdin"):
        try:
            main()
        except SystemExit:
            pass

    # Session should be saved with correct state
    assert len(saved_sessions) >= 1
    saved = saved_sessions[0]
    assert saved.in_plan_mode is True
    assert saved.initial_prompt == "Build an API"
    assert saved.iteration_count == 1
    assert saved.rag_done is True


def test_hook_rag_output(tmp_path, capsys):
    transcript = tmp_path / "transcript.jsonl"
    _write_transcript(transcript, [
        _make_user("Design a cache"),
        _make_assistant_tool_use("EnterPlanMode"),
    ])

    session = SessionState(session_id="test-session")
    project = ProjectConfig(
        project_name="test",
        project_uuid="proj-1",
        use_rag=True,
        top_k=3,
    )
    gc = GlobalConfig(default_scan_all_projects=True)

    mock_results = [{"plan_uuid": "plan-1", "similarity": 0.85}]

    hook_input = {
        "session_id": "test-session",
        "transcript_path": str(transcript),
        "cwd": "/some/dir",
    }

    with patch("planectra.hooks.plan_enter.load_session", return_value=session), \
         patch("planectra.hooks.plan_enter.save_session"), \
         patch("planectra.hooks.plan_enter.config.get_project_for_dir", return_value=project), \
         patch("planectra.hooks.plan_enter.config.load_global_config", return_value=gc), \
         patch("planectra.storage.vector.query_similar", return_value=mock_results) as mock_query, \
         patch("planectra.rag_format.format_rag_context", return_value="<planectra-context>test</planectra-context>") as mock_format, \
         patch("json.load", return_value=hook_input), \
         patch("sys.stdin"):
        main()

    captured = capsys.readouterr()
    assert "<planectra-context>" in captured.out
    mock_query.assert_called_once()
    mock_format.assert_called_once()


def test_hook_no_output_when_rag_disabled(tmp_path, capsys):
    transcript = tmp_path / "transcript.jsonl"
    _write_transcript(transcript, [
        _make_user("Design a cache"),
        _make_assistant_tool_use("EnterPlanMode"),
    ])

    session = SessionState(session_id="test-session")
    project = ProjectConfig(
        project_name="test",
        project_uuid="proj-1",
        use_rag=False,
    )

    hook_input = {
        "session_id": "test-session",
        "transcript_path": str(transcript),
        "cwd": "/some/dir",
    }

    with patch("planectra.hooks.plan_enter.load_session", return_value=session), \
         patch("planectra.hooks.plan_enter.save_session"), \
         patch("planectra.hooks.plan_enter.config.get_project_for_dir", return_value=project), \
         patch("json.load", return_value=hook_input), \
         patch("sys.stdin"):
        try:
            main()
        except SystemExit:
            pass

    captured = capsys.readouterr()
    assert captured.out == ""


def test_hook_no_output_when_no_project(tmp_path, capsys):
    transcript = tmp_path / "transcript.jsonl"
    _write_transcript(transcript, [
        _make_user("Design a cache"),
        _make_assistant_tool_use("EnterPlanMode"),
    ])

    session = SessionState(session_id="test-session")

    hook_input = {
        "session_id": "test-session",
        "transcript_path": str(transcript),
        "cwd": "/some/dir",
    }

    with patch("planectra.hooks.plan_enter.load_session", return_value=session), \
         patch("planectra.hooks.plan_enter.save_session"), \
         patch("planectra.hooks.plan_enter.config.get_project_for_dir", return_value=None), \
         patch("json.load", return_value=hook_input), \
         patch("sys.stdin"):
        try:
            main()
        except SystemExit:
            pass

    captured = capsys.readouterr()
    assert captured.out == ""


# --- prompt hook RAG injection tests (user-toggled plan mode) ---

def _run_prompt_hook(hook_input):
    """Run the prompt hook with the given input dict."""
    with patch("json.load", return_value=hook_input), \
         patch("sys.stdin"):
        prompt_main()


def test_prompt_hook_exits_when_not_plan_mode():
    """Should exit immediately when permission_mode is not 'plan'."""
    hook_input = {
        "session_id": "test",
        "permission_mode": "default",
        "prompt": "hello",
    }
    with patch("json.load", return_value=hook_input), \
         patch("sys.stdin"):
        try:
            prompt_main()
        except SystemExit as e:
            assert e.code == 0


def test_prompt_hook_sets_session_state_on_first_plan_prompt():
    """First prompt in plan mode should set session state like plan_enter does."""
    session = SessionState(session_id="test-session")
    saved_sessions = []

    hook_input = {
        "session_id": "test-session",
        "transcript_path": "",
        "cwd": "/some/dir",
        "permission_mode": "plan",
        "prompt": "Build a web server",
    }

    with patch("planectra.hooks.prompt.load_session", return_value=session), \
         patch("planectra.hooks.prompt.save_session", side_effect=saved_sessions.append), \
         patch("planectra.hooks.prompt.config.get_project_for_dir", return_value=None), \
         patch("json.load", return_value=hook_input), \
         patch("sys.stdin"):
        try:
            prompt_main()
        except SystemExit:
            pass

    assert len(saved_sessions) >= 1
    saved = saved_sessions[0]
    assert saved.in_plan_mode is True
    assert saved.initial_prompt == "Build a web server"
    assert saved.iteration_count == 1
    assert saved.rag_done is True


def test_prompt_hook_injects_rag_on_first_plan_prompt(capsys):
    """First prompt in plan mode should inject RAG context to stdout."""
    session = SessionState(session_id="test-session")
    project = ProjectConfig(
        project_name="test",
        project_uuid="proj-1",
        use_rag=True,
        top_k=3,
    )
    gc = GlobalConfig(default_scan_all_projects=True)
    mock_results = [{"plan_uuid": "plan-1", "similarity": 0.85}]

    hook_input = {
        "session_id": "test-session",
        "transcript_path": "",
        "cwd": "/some/dir",
        "permission_mode": "plan",
        "prompt": "Design a cache",
    }

    with patch("planectra.hooks.prompt.load_session", return_value=session), \
         patch("planectra.hooks.prompt.save_session"), \
         patch("planectra.hooks.prompt.config.get_project_for_dir", return_value=project), \
         patch("planectra.hooks.prompt.config.load_global_config", return_value=gc), \
         patch("planectra.storage.vector.query_similar", return_value=mock_results) as mock_query, \
         patch("planectra.rag_format.format_rag_context", return_value="<planectra-context>test</planectra-context>") as mock_format, \
         patch("json.load", return_value=hook_input), \
         patch("sys.stdin"):
        try:
            prompt_main()
        except SystemExit:
            pass

    captured = capsys.readouterr()
    assert "<planectra-context>" in captured.out
    mock_query.assert_called_once()
    mock_format.assert_called_once()


def test_prompt_hook_increments_iteration_on_subsequent_prompt():
    """Subsequent prompts in plan mode should increment iteration_count, not re-run RAG."""
    session = SessionState(session_id="test-session", rag_done=True, iteration_count=2)
    saved_sessions = []

    hook_input = {
        "session_id": "test-session",
        "transcript_path": "",
        "cwd": "/some/dir",
        "permission_mode": "plan",
        "prompt": "Add TTL support",
    }

    with patch("planectra.hooks.prompt.load_session", return_value=session), \
         patch("planectra.hooks.prompt.save_session", side_effect=saved_sessions.append), \
         patch("json.load", return_value=hook_input), \
         patch("sys.stdin"):
        try:
            prompt_main()
        except SystemExit:
            pass

    assert len(saved_sessions) == 1
    assert saved_sessions[0].iteration_count == 3


def test_prompt_hook_no_rag_when_no_project(capsys):
    """No RAG output when project is not configured."""
    session = SessionState(session_id="test-session")

    hook_input = {
        "session_id": "test-session",
        "transcript_path": "",
        "cwd": "/some/dir",
        "permission_mode": "plan",
        "prompt": "Design something",
    }

    with patch("planectra.hooks.prompt.load_session", return_value=session), \
         patch("planectra.hooks.prompt.save_session"), \
         patch("planectra.hooks.prompt.config.get_project_for_dir", return_value=None), \
         patch("json.load", return_value=hook_input), \
         patch("sys.stdin"):
        try:
            prompt_main()
        except SystemExit:
            pass

    captured = capsys.readouterr()
    assert captured.out == ""


def test_prompt_hook_no_rag_when_rag_disabled(capsys):
    """No RAG output when project has use_rag=False."""
    session = SessionState(session_id="test-session")
    project = ProjectConfig(
        project_name="test",
        project_uuid="proj-1",
        use_rag=False,
    )

    hook_input = {
        "session_id": "test-session",
        "transcript_path": "",
        "cwd": "/some/dir",
        "permission_mode": "plan",
        "prompt": "Design something",
    }

    with patch("planectra.hooks.prompt.load_session", return_value=session), \
         patch("planectra.hooks.prompt.save_session"), \
         patch("planectra.hooks.prompt.config.get_project_for_dir", return_value=project), \
         patch("json.load", return_value=hook_input), \
         patch("sys.stdin"):
        try:
            prompt_main()
        except SystemExit:
            pass

    captured = capsys.readouterr()
    assert captured.out == ""
