# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH

"""One-time takeover of the matrix-nio device by matrix-e2ee-cli.

Stdlib only. Up to version 4 this skill kept its E2EE device in a matrix-nio
store (``$XDG_DATA_HOME/matrix-skill/store``, default
``~/.local/share/matrix-skill/store``, with ``credentials.json`` in it). The
CLI converts that store into its own session with ``migrate-nio``, keeping the
device id, its identity keys (so its verification stays valid) and its room
keys. Logging in instead would mint a new, unverified device without them.

``migrate_if_pending`` runs before the first CLI command on a machine that
still has the nio store and no CLI session:

1. take the store's ``.daemon.lock`` without waiting (an old matrix-nio daemon
   or script still running holds it: stop and say so),
2. copy the whole store, ``credentials.json`` included, to
   ``store.backup-<UTC time>`` beside it (owner-only: it holds the access token),
3. run ``migrate-nio --yes --store <store>``, which only reads the nio store,
4. on success write ``nio-migrated.json`` in the skill's data directory, so a
   later ``logout`` never leads to a second takeover of a device that is gone.

A failure stops the command: nothing falls through to a login or to a command
that would run without the device.
"""

import contextlib
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

LOCK_NAME = ".daemon.lock"
CREDENTIALS = "credentials.json"
MARKER_NAME = "nio-migrated.json"


class CutoverError(Exception):
    """The takeover did not happen; the command must not run."""


def _data_home(env) -> Path:
    """$XDG_DATA_HOME, else ~/.local/share, as the nio skill and the CLI compute it."""
    xdg = env.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg)
    home = env.get("HOME")
    if not home:
        raise CutoverError("neither XDG_DATA_HOME nor HOME is set")
    return Path(home) / ".local" / "share"


def nio_store_path(env=None) -> Path:
    env = os.environ if env is None else env
    return _data_home(env) / "matrix-skill" / "store"


def marker_path(env=None) -> Path:
    env = os.environ if env is None else env
    return _data_home(env) / "matrix-skill" / MARKER_NAME


def cli_session_path(env=None) -> Path:
    """The CLI's session file on Linux and macOS (matrix-e2ee-cli session.rs)."""
    env = os.environ if env is None else env
    return _data_home(env) / "matrix-e2ee-cli" / "session.json"


def pending(env=None) -> bool:
    """True when a nio device waits for its takeover.

    The nio store holds credentials.json, no takeover was recorded, and the CLI
    has no session yet. matrix-nio ran on Linux and macOS only.
    """
    if os.name != "posix":
        return False
    env = os.environ if env is None else env
    try:
        store = nio_store_path(env)
        return (
            (store / CREDENTIALS).is_file()
            and not marker_path(env).exists()
            and not cli_session_path(env).exists()
        )
    except CutoverError:
        return False


def _holder_hint() -> str:
    """Name the old daemon's pid when it still answers on its socket."""
    try:
        from _lib.daemon_client import daemon_request, running_daemon_pid

        pid = running_daemon_pid(daemon_request({"op": "status"}, timeout=5.0))
    except Exception:  # noqa: BLE001  # only a hint; the refusal stands without it
        pid = None
    if pid:
        return f" The old matrix-watchd.py daemon answers as pid {pid}: stop it with `kill {pid}`."
    return ""


@contextlib.contextmanager
def store_lock(store: Path):
    """Hold the nio store's flock, or refuse at once when someone else holds it."""
    import fcntl

    path = store / LOCK_NAME
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise CutoverError(
                f"the matrix-nio store {store} is in use (its {LOCK_NAME} is held), most "
                "likely by the matrix-watchd.py daemon or an E2EE script of an older version "
                "of this skill. Stop that process, then run the command again."
                + _holder_hint()
            ) from None
        yield
    finally:
        os.close(fd)


def backup_store(store: Path, now=None) -> Path:
    """Copy STORE beside itself, owner-only; the copy's path."""
    now = now or datetime.now(UTC)
    base = store.parent / f"store.backup-{now.strftime('%Y%m%dT%H%M%SZ')}"
    target = base
    counter = 1
    while target.exists():
        target = Path(f"{base}.{counter}")
        counter += 1
    old_umask = os.umask(0o077)
    try:
        shutil.copytree(
            store, target, symlinks=True, ignore=shutil.ignore_patterns(LOCK_NAME)
        )
    finally:
        os.umask(old_umask)
    for root, dirs, files in os.walk(target):
        os.chmod(root, 0o700)
        for name in files:
            path = os.path.join(root, name)
            if not os.path.islink(path):
                os.chmod(path, 0o600)
    return target


def _notice(store: Path, backup: Path) -> str:
    return (
        "matrix-communication: this skill's E2EE device now runs in matrix-e2ee-cli "
        "(migrate-nio above).\n"
        f"  Backup of the old matrix-nio store, credentials.json included: {backup} "
        "(owner-only; it holds the access token).\n"
        f"  The skill no longer uses {store}. Skip the step that says "
        "`matrix-e2ee-setup.py --logout`: that script now refuses --logout. Once E2EE "
        "commands work, delete the old store yourself if you like; never log the device "
        "out on the server, that would end the migrated device too.\n"
        "  Older versions of this skill would still open the old store as the same "
        "device: do not run them on this machine."
    )


def migrate(binary, env=None, runner=subprocess.run, log=None) -> Path:
    """Back up the nio store and run migrate-nio; the backup's path."""
    env = os.environ if env is None else env
    log = log or (lambda message: print(message, file=sys.stderr, flush=True))
    store = nio_store_path(env)
    log(
        f"matrix-communication: taking over the matrix-nio device in {store} (one time)"
    )
    with store_lock(store):
        backup = backup_store(store)
    log(f"  Backup: {backup}")
    # stdout goes to stderr: callers parse the command's stdout (JSON, "Event ID: ...").
    result = runner(
        [str(binary), "migrate-nio", "--yes", "--store", str(store)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=dict(env),
        check=False,
    )
    if result.stdout:
        log(result.stdout.rstrip("\n"))
    if result.returncode != 0:
        raise CutoverError(
            f"migrate-nio failed (exit {result.returncode}); the command did not run. The "
            f"matrix-nio store is unchanged and a copy is in {backup}. To give up the old "
            f"device instead, move {store} away; the next E2EE command then needs "
            "matrix-e2ee-setup.py (a new device)."
        )
    marker = marker_path(env)
    marker.write_text(
        json.dumps(
            {
                "migrated_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "store": str(store),
                "backup": str(backup),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    log(_notice(store, backup))
    return backup


def migrate_if_pending(binary, env=None, runner=subprocess.run, log=None):
    """Run the takeover when one is pending; the backup path, or None."""
    if not pending(env):
        return None
    return migrate(binary, env=env, runner=runner, log=log)
