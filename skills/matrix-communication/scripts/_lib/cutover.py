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
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

LOCK_NAME = ".daemon.lock"
# Held for a whole takeover (backup, migrate-nio, marker), so a second process
# waits for it and then finds the takeover done instead of starting another.
TAKEOVER_LOCK = "takeover.lock"
CREDENTIALS = "credentials.json"
MARKER_NAME = "nio-migrated.json"


class CutoverError(Exception):
    """The takeover did not happen; the command must not run."""


def _data_home(env) -> Path:
    """$XDG_DATA_HOME, else <home>/.local/share, as the nio skill and the CLI compute it.

    <home> is HOME, else USERPROFILE (Windows), like the CLI's ``home_dir``.
    """
    xdg = env.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg)
    home = env.get("HOME") or env.get("USERPROFILE")
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
            and not _recorded(env)
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


@contextlib.contextmanager
def takeover_lock(env):
    """Hold the skill's takeover lock; waits while another process holds it.

    Not the nio store's own lock: migrate-nio takes that one itself and
    refuses while anybody else holds it.
    """
    import fcntl

    path = _data_home(env) / "matrix-skill" / TAKEOVER_LOCK
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
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


def tree_digest(root: Path) -> str:
    """SHA-256 over the relative paths and contents of ROOT's files.

    The store's own ``.daemon.lock`` is left out, as ``backup_store`` leaves it
    out of the copy; modes and times do not count.
    """
    digest = hashlib.sha256()
    for directory, dirs, files in os.walk(root):
        dirs.sort()
        for name in sorted(files):
            path = Path(directory, name)
            rel = path.relative_to(root)
            if str(rel) == LOCK_NAME:
                continue
            digest.update(str(rel).encode() + b"\0")
            if path.is_symlink():
                digest.update(b"link:" + os.readlink(path).encode() + b"\0")
            else:
                digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def existing_backups(store: Path) -> list:
    """The backups beside STORE, oldest first (their names sort by time)."""
    return sorted(p for p in store.parent.glob("store.backup-*") if p.is_dir())


def _posix() -> bool:
    """fcntl locks and migrate-nio exist on Linux and macOS only."""
    return os.name == "posix"


def _locked_backup(store: Path) -> Path:
    """reuse_or_backup under the store's lock; a copy that fails stops here."""
    with store_lock(store):
        try:
            return reuse_or_backup(store)
        except OSError as exc:  # shutil.Error is an OSError too
            raise CutoverError(
                f"cannot back up the matrix-nio store {store}: {exc}; migrate-nio did "
                "not run and the store is unchanged"
            ) from exc


def reuse_or_backup(store: Path) -> Path:
    """The newest backup when it still matches STORE's content, else a new one.

    A takeover that failed and is tried again would otherwise leave one more
    copy of credentials.json each time.
    """
    backups = existing_backups(store)
    if backups and tree_digest(backups[-1]) == tree_digest(store):
        return backups[-1]
    return backup_store(store)


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


def _marker_state(env):
    """None (no marker), "running" (a takeover may be under way) or "done"."""
    path = marker_path(env)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "done"  # unreadable: never risk a second takeover
    return "running" if isinstance(data, dict) and data.get("running") else "done"


def _recorded(env) -> bool:
    """A takeover is recorded: a marker that is not a takeover still running."""
    return _marker_state(env) == "done"


def settle(env=None) -> None:
    """Finish the record of a takeover whose process was killed mid-way.

    A "running" marker with a session beside it means migrate-nio created
    the session and the process ended before it could record that. Run
    before every command, so a later logout cannot reopen the takeover.
    """
    env = os.environ if env is None else env
    try:
        if _marker_state(env) == "running" and cli_session_path(env).exists():
            data = json.loads(marker_path(env).read_text(encoding="utf-8"))
            data.pop("running", None)
            marker_path(env).write_text(
                json.dumps(data, indent=2) + "\n", encoding="utf-8"
            )
    except (OSError, ValueError, CutoverError):
        pass  # the next command tries again; pending() stays false while a session exists


@contextlib.contextmanager
def _recording(env, store: Path, backup):
    """Record the takeover around a migrate-nio run, interruptions included.

    Without a session before the run, a "running" marker goes in first. Once
    the run is over, however it ended (an error, Ctrl-C), the marker is made
    final when a session exists and removed when none does. A kill in
    between leaves the "running" marker for settle() and pending() to read.
    """
    if cli_session_path(env).exists():
        yield
        return
    _write_marker(env, store, backup, running=True)
    try:
        yield
    finally:
        if cli_session_path(env).exists():
            _write_marker(env, store, backup)
        else:
            marker_path(env).unlink(missing_ok=True)


def _write_marker(env, store: Path, backup, running=False) -> None:
    marker_path(env).parent.mkdir(parents=True, exist_ok=True)
    marker_path(env).write_text(
        json.dumps(
            {
                "migrated_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "store": str(store),
                "backup": str(backup) if backup else None,
                **({"running": True} if running else {}),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def migrate(binary, env=None, runner=subprocess.run, log=None):
    """Back up the nio store and run migrate-nio; the backup's path.

    None when, once the takeover lock is held, nothing is pending any more:
    another process finished the takeover while this one waited.
    """
    env = os.environ if env is None else env
    log = log or (lambda message: print(message, file=sys.stderr, flush=True))
    store = nio_store_path(env)
    with takeover_lock(env):
        if not pending(env):
            return None
        log(
            "matrix-communication: taking over the matrix-nio device in "
            f"{store} (one time)"
        )
        backup = _locked_backup(store)
        log(f"  Backup: {backup}")
        return _run_migration(binary, env, runner, log, store, backup)


def _run_migration(binary, env, runner, log, store, backup):
    # stdout goes to stderr: callers parse the command's stdout (JSON, "Event ID: ...").
    with _recording(env, store, backup):
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
        copies = ", ".join(str(p) for p in existing_backups(store))
        raise CutoverError(
            f"migrate-nio failed (exit {result.returncode}); the command did not run. The "
            f"matrix-nio store is unchanged. Copies of it, each with credentials.json "
            f"(the access token), are in: {copies}. To give up the old "
            f"device instead, move {store} away; the next E2EE command then needs "
            "matrix-e2ee-setup.py (a new device)."
        )
    _write_marker(env, store, backup)  # a success is the takeover, session or not
    log(_notice(store, backup))
    return backup


def _store_argument(args, env) -> Path:
    """The store an explicit migrate-nio reads: its --store, else the default."""
    for index, arg in enumerate(args):
        if arg == "--":
            break
        if arg == "--store" and index + 1 < len(args):
            return Path(args[index + 1])
        if arg.startswith("--store="):
            return Path(arg.split("=", 1)[1])
    return nio_store_path(env)


def explicit_migrate(binary, args, env=None, run=None, log=None) -> int:
    """``matrix-e2ee-cli.py migrate-nio ...``: back up first, then run it as given.

    The arguments go to the CLI unchanged, so its question and --yes,
    --store and --check-online behave as documented. The store is copied
    first, as for the automatic takeover, and a run that created the session
    records the takeover, whatever its exit code. No copy, no migration: a
    failed backup stops here. Off Linux and macOS the CLI runs unchanged and
    refuses with its own message.
    """
    env = os.environ if env is None else env
    log = log or (lambda message: print(message, file=sys.stderr, flush=True))
    if run is None:
        from _lib.cli import run
    if not _posix():
        # No fcntl here; migrate-nio itself says it runs on Linux and macOS only.
        return run(binary, list(args), env=dict(env))
    store = _store_argument(args, env)
    with takeover_lock(env):
        backup = None
        if (store / CREDENTIALS).is_file():
            backup = _locked_backup(store)
            log(f"matrix-communication: backup of {store} before migrate-nio: {backup}")
        # Whatever the exit code: --check-online can fail after the session was
        # written, and that session is the device taken over.
        with _recording(env, store, backup):
            return run(binary, list(args), env=dict(env))


def migrate_if_pending(binary, env=None, runner=subprocess.run, log=None):
    """Run the takeover when one is pending; the backup path, or None.

    pending() is asked again inside migrate(), under the takeover lock.
    """
    settle(env)
    if not pending(env):
        return None
    return migrate(binary, env=env, runner=runner, log=log)
