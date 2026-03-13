"""File-based session state management."""
from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

from planectra.config import SESSIONS_DIR
from planectra.models import SessionState


def _session_path(session_id: str) -> Path:
    return SESSIONS_DIR / f"{session_id}.json"


def load_session(session_id: str) -> SessionState:
    """Load session state from disk, returning default if missing."""
    path = _session_path(session_id)
    if path.exists():
        data = json.loads(path.read_text())
        return SessionState(**data)
    return SessionState(session_id=session_id)


def save_session(state: SessionState) -> None:
    """Atomic write of session state via tempfile + os.replace()."""
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    path = _session_path(state.session_id)
    fd, tmp_path = tempfile.mkstemp(dir=SESSIONS_DIR, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps(state.model_dump(), indent=2))
        os.replace(tmp_path, path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def delete_session(session_id: str) -> None:
    """Remove session file."""
    path = _session_path(session_id)
    if path.exists():
        path.unlink()


def cleanup_stale_sessions(max_age_hours: int = 24) -> int:
    """Delete session files older than max_age_hours. Returns count deleted."""
    if not SESSIONS_DIR.exists():
        return 0
    cutoff = time.time() - max_age_hours * 3600
    deleted = 0
    for path in SESSIONS_DIR.glob("*.json"):
        if path.stat().st_mtime < cutoff:
            path.unlink()
            deleted += 1
    return deleted
