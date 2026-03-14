from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from planectra.config import ensure_dirs

PLANECTRA_HOOKS = {
    "UserPromptSubmit": [
        {
            "hooks": [{"type": "command", "command": "planectra-hook-prompt", "timeout": 10}],
        }
    ],
    "PostToolUse": [
        {
            "matcher": "EnterPlanMode",
            "hooks": [{"type": "command", "command": "planectra-hook-plan-enter", "timeout": 10}],
        },
    ],
    "PreToolUse": [
        {
            "matcher": "ExitPlanMode",
            "hooks": [{"type": "command", "command": "planectra-hook-plan-exit", "timeout": 10}],
        }
    ],
    "SessionStart": [
        {
            "hooks": [{
                "type": "command",
                "command": "planectra-hook-session",
                "timeout": 5,
                "statusMessage": "[Planectra] Initializing...",
            }],
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


def _resolve_paths(scope: str) -> tuple[Path, Path]:
    """Return (settings_path, claude_md_path) based on scope."""
    base = Path(os.getcwd()) / ".claude" if scope == "project" else Path.home() / ".claude"
    return base / "settings.json", base / "CLAUDE.md"


def install(scope: str = "global") -> str:
    """Install Planectra hooks and MCP server.

    Args:
        scope: "global" for ~/.claude/ or "project" for ./.claude/ in cwd.
    """
    settings_path, claude_md_path = _resolve_paths(scope)
    scope_label = "~/.claude" if scope == "global" else ".claude (project-local)"
    messages = []

    ensure_dirs()
    messages.append("Created ~/.planectra/ directory structure")

    _merge_hooks(settings_path)
    messages.append(f"Added hooks to {scope_label}/settings.json")

    mcp_scope = [] if scope == "global" else ["--scope", "project"]
    _register_mcp_server(mcp_scope)
    messages.append(f"Registered MCP server ({scope})")

    _add_claude_md_instructions(claude_md_path)
    messages.append(f"Added instructions to {scope_label}/CLAUDE.md")

    return "\n".join(messages)


def uninstall(scope: str = "global") -> str:
    """Remove Planectra hooks and MCP server.

    Args:
        scope: "global" for ~/.claude/ or "project" for ./.claude/ in cwd.
    """
    settings_path, claude_md_path = _resolve_paths(scope)
    scope_label = "~/.claude" if scope == "global" else ".claude (project-local)"
    messages = []

    _remove_hooks(settings_path)
    messages.append(f"Removed hooks from {scope_label}/settings.json")

    mcp_scope = [] if scope == "global" else ["--scope", "project"]
    try:
        subprocess.run(
            ["claude", "mcp", "remove", *mcp_scope, "planectra"],
            capture_output=True,
            timeout=10,
        )
        messages.append("Unregistered MCP server")
    except Exception as e:
        messages.append(f"Warning: Could not unregister MCP server: {e}")

    _remove_claude_md_instructions(claude_md_path)
    messages.append(f"Removed instructions from {scope_label}/CLAUDE.md")

    messages.append("\nNote: ~/.planectra/ data directory preserved. Delete manually if desired.")
    return "\n".join(messages)


def _merge_hooks(settings_path: Path) -> None:
    """Merge Planectra hooks into Claude settings without overwriting existing hooks."""
    settings: dict = {}
    if settings_path.exists():
        settings = json.loads(settings_path.read_text())

    hooks = settings.get("hooks", {})

    for event, hook_list in PLANECTRA_HOOKS.items():
        existing = hooks.get(event, [])
        existing = [h for h in existing if not _is_planectra_hook(h)]
        existing.extend(hook_list)
        hooks[event] = existing

    settings["hooks"] = hooks
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(settings, indent=2))


def _remove_hooks(settings_path: Path) -> None:
    """Remove Planectra hooks from Claude settings."""
    if not settings_path.exists():
        return

    settings = json.loads(settings_path.read_text())
    hooks = settings.get("hooks", {})

    for event in list(hooks.keys()):
        hooks[event] = [h for h in hooks[event] if not _is_planectra_hook(h)]
        if not hooks[event]:
            del hooks[event]

    if hooks:
        settings["hooks"] = hooks
    elif "hooks" in settings:
        del settings["hooks"]

    settings_path.write_text(json.dumps(settings, indent=2))


def _is_planectra_hook(hook_entry: dict) -> bool:
    """Check if a hook entry belongs to Planectra."""
    for h in hook_entry.get("hooks", []):
        cmd = h.get("command", "")
        if "planectra" in cmd:
            return True
    return False


def _register_mcp_server(scope_args: list[str]) -> None:
    """Register Planectra as an MCP server with Claude Code."""
    cmd = [
        "claude", "mcp", "add",
        *scope_args,
        "--transport", "stdio",
        "planectra", "--",
        "planectra-mcp-server",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=10)
        if result.returncode != 0:
            subprocess.run(
                ["claude", "mcp", "remove", *scope_args, "planectra"], capture_output=True, timeout=10
            )
            subprocess.run(cmd, capture_output=True, timeout=10)
    except FileNotFoundError:
        pass  # claude CLI not found



def _add_claude_md_instructions(claude_md_path: Path) -> None:
    """Add Planectra instructions to CLAUDE.md."""
    content = ""
    if claude_md_path.exists():
        content = claude_md_path.read_text()

    if "Planectra - Planning Conversation Tracker" in content:
        _remove_claude_md_instructions(claude_md_path)
        content = claude_md_path.read_text() if claude_md_path.exists() else ""

    claude_md_path.parent.mkdir(parents=True, exist_ok=True)
    claude_md_path.write_text(content.rstrip() + "\n" + CLAUDE_MD_SECTION)


def _remove_claude_md_instructions(claude_md_path: Path) -> None:
    """Remove Planectra section from CLAUDE.md."""
    if not claude_md_path.exists():
        return

    content = claude_md_path.read_text()
    marker = "## Planectra - Planning Conversation Tracker"
    if marker not in content:
        return

    idx = content.index(marker)
    rest = content[idx + len(marker) :]
    next_heading = rest.find("\n## ")
    end = idx + len(marker) + next_heading if next_heading != -1 else len(content)

    content = content[:idx].rstrip() + content[end:]
    claude_md_path.write_text(content.strip() + "\n" if content.strip() else "")
