import json
from unittest.mock import patch

from planectra.hooks.session import main
from planectra.models import ProjectConfig


def _run_session_hook(hook_input, capsys):
    """Run the session hook, return parsed JSON output."""
    with patch("json.load", return_value=hook_input), \
         patch("sys.stdin"), \
         patch("planectra.hooks.session.cleanup_stale_sessions"):
        main()
    captured = capsys.readouterr()
    return json.loads(captured.out), captured.err


def test_configured_project_notification(capsys):
    """Configured project → JSON with systemMessage and additionalContext."""
    project = ProjectConfig(
        project_name="my-app",
        project_uuid="uuid-1",
    )
    hook_input = {"cwd": "/home/user/my-app"}

    with patch("planectra.hooks.session.config.get_project_for_dir", return_value=project):
        output, stderr = _run_session_hook(hook_input, capsys)

    assert output["systemMessage"] == "[Planectra] Project: my-app"
    ctx = output["hookSpecificOutput"]["additionalContext"]
    assert "[Planectra] Project: my-app" in ctx
    assert "Inform the user" in ctx
    assert 'plan tracking for project "my-app"' in ctx
    assert stderr == ""


def test_unconfigured_no_existing_projects(capsys):
    """Unconfigured, no existing projects → init directive + suggested name."""
    hook_input = {"cwd": "/home/user/cool-project"}

    with patch("planectra.hooks.session.config.get_project_for_dir", return_value=None), \
         patch("planectra.hooks.session.config.list_all_projects", return_value=[]):
        output, stderr = _run_session_hook(hook_input, capsys)

    assert output["systemMessage"] == "[Planectra] No project configured"
    ctx = output["hookSpecificOutput"]["additionalContext"]
    assert "IMPORTANT:" in ctx
    assert "ask them if they'd like to enable" in ctx
    assert '"cool-project"' in ctx
    assert '"/home/user/cool-project"' in ctx
    assert "Do not ask again in this session" in ctx
    assert "Existing projects" not in ctx
    assert stderr == ""


def test_unconfigured_with_existing_projects(capsys):
    """Unconfigured, with existing projects → init directive + project list."""
    existing = [
        ProjectConfig(project_name="alpha", project_uuid="uuid-alpha"),
        ProjectConfig(project_name="beta", project_uuid="uuid-beta"),
    ]
    hook_input = {"cwd": "/home/user/new-dir"}

    with patch("planectra.hooks.session.config.get_project_for_dir", return_value=None), \
         patch("planectra.hooks.session.config.list_all_projects", return_value=existing):
        output, _stderr = _run_session_hook(hook_input, capsys)

    assert output["systemMessage"] == "[Planectra] No project configured"
    ctx = output["hookSpecificOutput"]["additionalContext"]
    assert "IMPORTANT:" in ctx
    assert '"new-dir"' in ctx
    assert "Existing projects" in ctx
    assert "alpha (UUID: uuid-alpha)" in ctx
    assert "beta (UUID: uuid-beta)" in ctx


def test_root_cwd_fallback(capsys):
    """Root cwd → falls back to 'my-project'."""
    hook_input = {"cwd": "/"}

    with patch("planectra.hooks.session.config.get_project_for_dir", return_value=None), \
         patch("planectra.hooks.session.config.list_all_projects", return_value=[]):
        output, _stderr = _run_session_hook(hook_input, capsys)

    ctx = output["hookSpecificOutput"]["additionalContext"]
    assert '"my-project"' in ctx


def test_empty_cwd_fallback(capsys):
    """Empty cwd string → falls back to 'my-project'."""
    hook_input = {"cwd": ""}

    with patch("planectra.hooks.session.config.get_project_for_dir", return_value=None), \
         patch("planectra.hooks.session.config.list_all_projects", return_value=[]):
        output, _stderr = _run_session_hook(hook_input, capsys)

    ctx = output["hookSpecificOutput"]["additionalContext"]
    assert '"my-project"' in ctx
