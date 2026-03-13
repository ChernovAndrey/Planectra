from __future__ import annotations

import json
import subprocess
from pathlib import Path

from planectra.config import ensure_dirs

CLAUDE_SETTINGS_PATH = Path.home() / ".claude" / "settings.json"
CLAUDE_MD_PATH = Path.home() / ".claude" / "CLAUDE.md"

PLANECTRA_HOOKS = {
    "UserPromptSubmit": [
        {
            "hooks": [{"type": "command", "command": "planectra-hook-prompt", "timeout": 10}],
        }
    ],
    "PostToolUse": [
        {
            "matcher": "ExitPlanMode",
            "hooks": [{"type": "command", "command": "planectra-hook-plan-exit", "timeout": 10}],
        }
    ],
    "SessionStart": [
        {
            "hooks": [{"type": "command", "command": "planectra-hook-session", "timeout": 5}],
        }
    ],
}

CLAUDE_MD_SECTION = """
## Planectra - Planning Conversation Tracker

After a plan is accepted (ExitPlanMode), call `planectra_finalize_plan` with your reflection:

- **plan_uuid**: Provided in the Planectra hook message after plan acceptance
- **plan_issues**: What was wrong/missing in earlier plan drafts
- **improvement_summary**: What key changes made the final plan better
- **rag_usefulness**: Was the retrieved RAG context useful? Why/why not? (skip if no RAG context was shown)

If the project has `include_user_comment` enabled, ask the user for optional feedback before calling.
"""


def install() -> str:
    """Install Planectra hooks and MCP server."""
    messages = []

    ensure_dirs()
    messages.append("Created ~/.planectra/ directory structure")

    _merge_hooks()
    messages.append("Added hooks to ~/.claude/settings.json")

    _register_mcp_server()
    messages.append("Registered MCP server")

    _add_claude_md_instructions()
    messages.append("Added instructions to ~/.claude/CLAUDE.md")

    return "\n".join(messages)


def uninstall() -> str:
    """Remove Planectra hooks and MCP server."""
    messages = []

    _remove_hooks()
    messages.append("Removed hooks from ~/.claude/settings.json")

    try:
        subprocess.run(
            ["claude", "mcp", "remove", "planectra"],
            capture_output=True,
            timeout=10,
        )
        messages.append("Unregistered MCP server")
    except Exception as e:
        messages.append(f"Warning: Could not unregister MCP server: {e}")

    _remove_claude_md_instructions()
    messages.append("Removed instructions from ~/.claude/CLAUDE.md")

    messages.append("\nNote: ~/.planectra/ data directory preserved. Delete manually if desired.")
    return "\n".join(messages)


def _merge_hooks() -> None:
    """Merge Planectra hooks into Claude settings without overwriting existing hooks."""
    settings: dict = {}
    if CLAUDE_SETTINGS_PATH.exists():
        settings = json.loads(CLAUDE_SETTINGS_PATH.read_text())

    hooks = settings.get("hooks", {})

    for event, hook_list in PLANECTRA_HOOKS.items():
        existing = hooks.get(event, [])
        # Remove any existing planectra hooks first
        existing = [h for h in existing if not _is_planectra_hook(h)]
        existing.extend(hook_list)
        hooks[event] = existing

    settings["hooks"] = hooks
    CLAUDE_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    CLAUDE_SETTINGS_PATH.write_text(json.dumps(settings, indent=2))


def _remove_hooks() -> None:
    """Remove Planectra hooks from Claude settings."""
    if not CLAUDE_SETTINGS_PATH.exists():
        return

    settings = json.loads(CLAUDE_SETTINGS_PATH.read_text())
    hooks = settings.get("hooks", {})

    for event in list(hooks.keys()):
        hooks[event] = [h for h in hooks[event] if not _is_planectra_hook(h)]
        if not hooks[event]:
            del hooks[event]

    if hooks:
        settings["hooks"] = hooks
    elif "hooks" in settings:
        del settings["hooks"]

    CLAUDE_SETTINGS_PATH.write_text(json.dumps(settings, indent=2))


def _is_planectra_hook(hook_entry: dict) -> bool:
    """Check if a hook entry belongs to Planectra."""
    for h in hook_entry.get("hooks", []):
        cmd = h.get("command", "")
        if "planectra" in cmd:
            return True
    return False


def _register_mcp_server() -> None:
    """Register Planectra as an MCP server with Claude Code."""
    cmd = [
        "claude", "mcp", "add",
        "--transport", "stdio",
        "planectra", "--",
        "planectra-mcp-server",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=10)
        if result.returncode != 0:
            # Might already exist — remove and re-add
            subprocess.run(["claude", "mcp", "remove", "planectra"], capture_output=True, timeout=10)
            subprocess.run(cmd, capture_output=True, timeout=10)
    except FileNotFoundError:
        pass  # claude CLI not found


def _add_claude_md_instructions() -> None:
    """Add Planectra instructions to ~/.claude/CLAUDE.md."""
    content = ""
    if CLAUDE_MD_PATH.exists():
        content = CLAUDE_MD_PATH.read_text()

    if "Planectra - Planning Conversation Tracker" in content:
        _remove_claude_md_instructions()
        content = CLAUDE_MD_PATH.read_text() if CLAUDE_MD_PATH.exists() else ""

    CLAUDE_MD_PATH.parent.mkdir(parents=True, exist_ok=True)
    CLAUDE_MD_PATH.write_text(content.rstrip() + "\n" + CLAUDE_MD_SECTION)


def _remove_claude_md_instructions() -> None:
    """Remove Planectra section from CLAUDE.md."""
    if not CLAUDE_MD_PATH.exists():
        return

    content = CLAUDE_MD_PATH.read_text()
    marker = "## Planectra - Planning Conversation Tracker"
    if marker not in content:
        return

    idx = content.index(marker)
    rest = content[idx + len(marker) :]
    next_heading = rest.find("\n## ")
    end = idx + len(marker) + next_heading if next_heading != -1 else len(content)

    content = content[:idx].rstrip() + content[end:]
    CLAUDE_MD_PATH.write_text(content.strip() + "\n" if content.strip() else "")
