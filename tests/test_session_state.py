import time

from planectra import config
from planectra.models import SessionState
from planectra.session_state import (
    cleanup_stale_sessions,
    delete_session,
    load_session,
    save_session,
)


def test_load_missing_session(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SESSIONS_DIR", tmp_path / "sessions")
    from planectra import session_state

    monkeypatch.setattr(session_state, "SESSIONS_DIR", tmp_path / "sessions")
    (tmp_path / "sessions").mkdir()

    session = load_session("nonexistent-id")
    assert session.session_id == "nonexistent-id"
    assert session.in_plan_mode is False
    assert session.rag_done is False
    assert session.iteration_count == 0


def test_save_and_load_roundtrip(tmp_path, monkeypatch):
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    monkeypatch.setattr(config, "SESSIONS_DIR", sessions_dir)
    from planectra import session_state

    monkeypatch.setattr(session_state, "SESSIONS_DIR", sessions_dir)

    state = SessionState(
        session_id="test-session",
        in_plan_mode=True,
        rag_done=True,
        initial_prompt="Design auth system",
        iteration_count=3,
        retrieved_plan_uuids=["plan-1", "plan-2"],
        transcript_path="/tmp/transcript.jsonl",
    )
    save_session(state)

    loaded = load_session("test-session")
    assert loaded.session_id == "test-session"
    assert loaded.in_plan_mode is True
    assert loaded.rag_done is True
    assert loaded.initial_prompt == "Design auth system"
    assert loaded.iteration_count == 3
    assert loaded.retrieved_plan_uuids == ["plan-1", "plan-2"]
    assert loaded.transcript_path == "/tmp/transcript.jsonl"


def test_delete_session(tmp_path, monkeypatch):
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    from planectra import session_state

    monkeypatch.setattr(session_state, "SESSIONS_DIR", sessions_dir)

    state = SessionState(session_id="to-delete")
    save_session(state)
    assert (sessions_dir / "to-delete.json").exists()

    delete_session("to-delete")
    assert not (sessions_dir / "to-delete.json").exists()

    # Deleting non-existent session should not error
    delete_session("to-delete")


def test_cleanup_stale_sessions(tmp_path, monkeypatch):
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    from planectra import session_state

    monkeypatch.setattr(session_state, "SESSIONS_DIR", sessions_dir)

    # Create a "stale" session file with old mtime
    state = SessionState(session_id="old-session")
    save_session(state)
    old_path = sessions_dir / "old-session.json"
    # Set mtime to 48 hours ago
    old_time = time.time() - 48 * 3600
    import os

    os.utime(old_path, (old_time, old_time))

    # Create a fresh session
    state2 = SessionState(session_id="fresh-session")
    save_session(state2)

    deleted = cleanup_stale_sessions(max_age_hours=24)
    assert deleted == 1
    assert not old_path.exists()
    assert (sessions_dir / "fresh-session.json").exists()


def test_atomic_write_creates_dir(tmp_path, monkeypatch):
    sessions_dir = tmp_path / "sessions"
    # Don't create the dir — save_session should handle it
    from planectra import session_state

    monkeypatch.setattr(session_state, "SESSIONS_DIR", sessions_dir)

    state = SessionState(session_id="auto-dir")
    save_session(state)
    assert (sessions_dir / "auto-dir.json").exists()
