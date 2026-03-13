from __future__ import annotations

import contextlib
import json
import os
import socket
import threading
from collections.abc import Callable

from planectra.config import SOCKET_PATH


def start_ipc_server(handler: Callable[[dict], dict]) -> threading.Thread | None:
    """Start Unix socket IPC server in a background thread.

    Returns the server thread, or None if the socket is already in use.
    """
    sock_path = str(SOCKET_PATH)

    # Clean up stale socket
    if os.path.exists(sock_path):
        try:
            test_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            test_sock.settimeout(1)
            test_sock.connect(sock_path)
            test_sock.close()
            # Socket is in use by another process
            return None
        except (ConnectionRefusedError, OSError):
            os.unlink(sock_path)

    server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server_sock.bind(sock_path)
    server_sock.listen(5)

    def serve():
        while True:
            try:
                conn, _ = server_sock.accept()
                threading.Thread(
                    target=_handle_connection,
                    args=(conn, handler),
                    daemon=True,
                ).start()
            except OSError:
                break

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    return thread


def _handle_connection(conn: socket.socket, handler: Callable[[dict], dict]) -> None:
    """Handle a single IPC connection."""
    try:
        data = b""
        while True:
            chunk = conn.recv(65536)
            if not chunk:
                break
            data += chunk
            if b"\n" in data:
                break

        if data:
            request = json.loads(data.decode("utf-8").strip())
            response = handler(request)
            conn.sendall(json.dumps(response).encode("utf-8") + b"\n")
    except Exception as e:
        try:
            error_resp = json.dumps({"status": "error", "message": str(e)}).encode("utf-8") + b"\n"
            conn.sendall(error_resp)
        except Exception:
            pass
    finally:
        conn.close()


def ipc_request(request: dict, timeout: float = 5.0) -> dict:
    """Send a request to the IPC server and return the response."""
    sock_path = str(SOCKET_PATH)

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect(sock_path)
        sock.sendall(json.dumps(request).encode("utf-8") + b"\n")

        data = b""
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            data += chunk
            if b"\n" in data:
                break

        return json.loads(data.decode("utf-8").strip())
    except (ConnectionRefusedError, FileNotFoundError, OSError):
        return {"status": "error", "message": "MCP server not running"}
    except TimeoutError:
        return {"status": "error", "message": "IPC timeout"}
    finally:
        sock.close()


def cleanup_socket() -> None:
    """Remove the socket file."""
    sock_path = str(SOCKET_PATH)
    if os.path.exists(sock_path):
        with contextlib.suppress(OSError):
            os.unlink(sock_path)
