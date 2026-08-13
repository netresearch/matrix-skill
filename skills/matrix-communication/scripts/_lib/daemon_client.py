"""Client side of the watch daemon's socket.

Stdlib only.

`daemon_request` returning None is the signal to fall back to the direct path:
it means nothing is serving the socket. That is a different question from
whether the store lock is held, and only this one may decide the routing - a
short-lived direct send holds the lock too, so a command starting in that window
would conclude "daemon is running" and talk to a socket nobody answers.

An error *response* is not None. It is an answer, and returning None for it
would send the caller down the direct path as well, delivering the message
twice.
"""

import json
import os
import socket
from pathlib import Path

CONNECT_TIMEOUT = 2.0


def socket_path() -> Path:
    """Where the daemon listens.

    The runtime directory when it is usable: it is cleared on reboot, which is
    exactly the lifetime a socket should have. `XDG_RUNTIME_DIR` being set is
    not the same as it existing - on WSL and in containers it is routinely
    exported for a `/run/user/<uid>` nobody created - so the directory is
    tested rather than trusted, and the fall-back is the data directory the
    rest of the skill already uses.
    """
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if runtime and os.path.isdir(runtime) and os.access(runtime, os.W_OK):
        base = Path(runtime)
    else:
        base = Path.home() / ".local" / "share"
    return base / "matrix-skill" / "daemon.sock"


def daemon_request(payload: dict, timeout: float = 30.0):
    """One request, one response. None when no daemon is listening."""
    path = socket_path()
    if not path.exists():
        return None

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(CONNECT_TIMEOUT)
    try:
        sock.connect(str(path))
    except OSError:
        # Stale socket from a crashed daemon, or none at all. Either way there
        # is nobody to delegate to.
        return None

    try:
        sock.settimeout(timeout)
        sock.sendall(json.dumps(payload).encode("utf-8") + b"\n")
        buffer = b""
        while not buffer.endswith(b"\n"):
            chunk = sock.recv(4096)
            if not chunk:
                break
            buffer += chunk
        if not buffer.strip():
            return None
        return json.loads(buffer)
    except (OSError, ValueError):
        return None
    finally:
        sock.close()
