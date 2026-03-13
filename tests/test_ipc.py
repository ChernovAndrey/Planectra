import os
import time

from planectra.server.ipc import cleanup_socket, ipc_request, start_ipc_server


def test_ipc_roundtrip(monkeypatch):
    # Use /tmp for short socket paths (macOS AF_UNIX 104-char limit)
    sock_path = f"/tmp/planectra_test_{os.getpid()}.sock"
    from pathlib import Path

    from planectra.server import ipc

    monkeypatch.setattr(ipc, "SOCKET_PATH", Path(sock_path))

    def handler(request):
        return {"status": "ok", "echo": request.get("message")}

    thread = start_ipc_server(handler)
    assert thread is not None
    time.sleep(0.1)

    try:
        response = ipc_request({"message": "hello"})
        assert response["status"] == "ok"
        assert response["echo"] == "hello"
    finally:
        cleanup_socket()


def test_ipc_server_not_running(tmp_path, monkeypatch):

    from planectra.server import ipc

    monkeypatch.setattr(ipc, "SOCKET_PATH", tmp_path / "nonexistent.sock")

    response = ipc_request({"action": "test"})
    assert response["status"] == "error"
    assert "not running" in response["message"]


def test_ipc_handler_error(monkeypatch):
    sock_path = f"/tmp/planectra_test_err_{os.getpid()}.sock"
    from pathlib import Path

    from planectra.server import ipc

    monkeypatch.setattr(ipc, "SOCKET_PATH", Path(sock_path))

    def bad_handler(request):
        raise ValueError("test error")

    thread = start_ipc_server(bad_handler)
    assert thread is not None
    time.sleep(0.1)

    try:
        response = ipc_request({"action": "test"})
        assert response["status"] == "error"
        assert "test error" in response["message"]
    finally:
        cleanup_socket()
