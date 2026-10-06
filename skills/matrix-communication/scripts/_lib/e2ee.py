# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH

"""E2EE credential management for Matrix scripts.

All functions use ONLY stdlib - no nio dependencies here.
The actual E2EE functionality (using nio) is in the scripts themselves.
"""

import atexit
import contextlib
import errno
import fcntl
import json
import os
import time
from contextlib import contextmanager
from pathlib import Path


def private_dir(path: Path) -> Path:
    """Create ``path`` if needed and make it accessible to its owner only.

    The mode is applied on every call, not only on creation, so a directory an
    older version created with the default umask is tightened on first use.
    Everything below it - credentials, the nio store, decrypted room logs -
    is then out of reach of other local users whatever the files' own modes.
    """
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path, 0o700)
    return path


def write_private_file(path: Path, data: str) -> None:
    """Write ``data`` to ``path`` readable and writable by the owner only.

    The file is created with mode 0600 rather than chmod-ed after the write,
    an existing file is tightened before anything is written to it, and a
    symlink at ``path`` is refused instead of followed.
    """
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        os.fchmod(handle.fileno(), 0o600)
        handle.write(data)


def get_store_path() -> Path:
    """Get or create the E2EE key store directory.

    Uses XDG_DATA_HOME or falls back to ~/.local/share/matrix-skill/store.
    The ``matrix-skill`` directory and the store are owner-only (0700).
    """
    xdg_data = os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")
    root = private_dir(Path(xdg_data) / "matrix-skill")
    return private_dir(root / "store")


def rooms_dir() -> Path:
    """Directory holding the per-room event logs and the room bundle.

    A sibling of the E2EE store rather than a child: nothing in here is
    device-scoped, and `--logout` must not carry a room's history away with the
    device it was recorded on.
    """
    return private_dir(get_store_path().parent / "rooms")


def verification_partner_allowed(sender, own_user_id, accept_from=()) -> bool:
    """Whether a verification event from ``sender`` may be answered.

    matrix-e2ee-verify.py confirms the short authentication string on its own
    side; the comparison is done by the person at the other device. That is
    sound for the account's own devices, where that person is the owner. For
    another user's device it would mark that device verified on the strength
    of a check only its owner made, so it is answered only for users named
    explicitly (``--accept-from``).
    """
    if not sender:
        return False
    return sender == own_user_id or sender in accept_from


def verification_emoji_path() -> Path:
    """Where matrix-e2ee-verify.py writes the emojis for an agent to poll."""
    return get_store_path().parent / "verification_emojis.txt"


def get_credentials_path() -> Path:
    """Get path for stored E2EE device credentials."""
    return get_store_path() / "credentials.json"


def load_credentials() -> dict | None:
    """Load stored device credentials if they exist.

    Returns:
        Dict with user_id, device_id, access_token, or None if not found
    """
    creds_path = get_credentials_path()
    if creds_path.exists():
        with open(creds_path) as f:
            return json.load(f)
    return None


def save_credentials(user_id: str, device_id: str, access_token: str):
    """Save device credentials for future use.

    The file is created with mode 0600 (see ``write_private_file``).
    """
    write_private_file(
        get_credentials_path(),
        json.dumps(
            {
                "user_id": user_id,
                "device_id": device_id,
                "access_token": access_token,
            },
            indent=2,
        ),
    )


LOCK_TIMEOUT = 30.0

# How deep this process is inside store_lock(). flock is held per open file
# description, so a process taking it twice on two descriptors blocks on
# itself - which the daemon would do the moment it called a helper that locks.
_LOCK_DEPTH = 0


def store_lock_path():
    """The file whose flock stands for the right to open the E2EE store."""
    return get_store_path() / ".daemon.lock"


@contextmanager
def store_lock(timeout: float = LOCK_TIMEOUT):
    """Hold the exclusive right to open the E2EE store, or refuse.

    Two nio processes on one store corrupt it, and the corruption does not
    announce itself - it surfaces later as an undecryptable message or a store
    that no longer opens. The daemon holds this lock for its whole run; every
    direct path takes it too, so the collision becomes a wait and then a clear
    refusal instead of silent damage.

    Blocking rather than failing at once: a direct send that arrives during
    another command's couple of seconds should wait for it, not error. On
    timeout the holder's pid is named, because the useful next question is
    always "who has it".
    """
    global _LOCK_DEPTH

    if _LOCK_DEPTH:
        # Already ours. Re-entering is what happens when a locked command calls
        # a helper that locks; the alternative is a process deadlocking itself.
        _LOCK_DEPTH += 1
        try:
            yield
        finally:
            _LOCK_DEPTH -= 1
        return

    path = store_lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(path, "a+")  # noqa: SIM115  # released in the finally below
    deadline = time.monotonic() + timeout

    while True:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except OSError as exc:
            if exc.errno not in (errno.EACCES, errno.EAGAIN):
                handle.close()
                raise
            if time.monotonic() >= deadline:
                handle.seek(0)
                holder = handle.read().strip() or "unknown"
                handle.close()
                raise SystemExit(
                    f"Error: the E2EE store is held by pid {holder}.\n"
                    "\n"
                    "That is normally matrix-watchd. Commands that route through "
                    "it - send, react, redact, edit - work while it runs; this "
                    "one does not yet. Stop the daemon for the duration:\n"
                    "  matrix-watchd.py --stop && … && matrix-watchd.py --start"
                ) from exc
            time.sleep(0.2)

    handle.seek(0)
    handle.truncate()
    handle.write(str(os.getpid()))
    handle.flush()

    _LOCK_DEPTH = 1
    try:
        yield
    finally:
        _LOCK_DEPTH = 0
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def explain_store_error(exc: Exception) -> str | None:
    """Diagnose a store that cannot be opened, or return None.

    A store written by one matrix-nio crypto backend cannot be read by the
    other: 0.25 serializes the olm account through libolm, 0.26 through
    vodozemac, and the two formats are not interchangeable. The failure surfaces
    as ``OlmAccountError: BAD_ACCOUNT_KEY``, which names a key, so the search
    goes to credentials.json, to the token, to the store path - none of which
    are wrong. Say what actually happened instead.

    Stdlib only, deliberately: this module must not import nio, so the exception
    is identified by type name and message rather than by class.
    """
    if "BAD_ACCOUNT_KEY" not in str(exc):
        return None
    if type(exc).__name__ not in ("OlmAccountError", "SessionError"):
        return None

    try:
        from importlib.metadata import version

        installed = version("matrix-nio")
    except Exception:  # noqa: BLE001  # diagnosis must not fail on a metadata lookup
        installed = "unknown"

    return (
        f"The E2EE store cannot be opened by the installed matrix-nio ({installed}).\n"
        "\n"
        "This is a backend mismatch, not a bad credential: matrix-nio 0.25 keeps "
        "the olm account in libolm's format and 0.26 in vodozemac's, and neither "
        "can read the other's. The store was written by the other one.\n"
        "\n"
        "The usual writer is a script copy from an OLDER skill version - a plugin\n"
        "cache directory or a stale checkout - whose unpinned dependency resolves\n"
        "the newest matrix-nio. Find and stop that source first (do NOT fall back\n"
        "to it as a workaround), or the store flips back after every re-setup.\n"
        "\n"
        "Run every script on the same pin. If the pin has moved, the store has to "
        "be recreated - it cannot be migrated:\n"
        "  matrix-e2ee-setup.py --logout && matrix-e2ee-setup.py\n"
        "  matrix-key-backup.py --import-keys\n"
        "  matrix-e2ee-verify.py --listen   # or --request DEVICE with a single Element session"
    )


def _hold_store_lock() -> None:
    """Take the store lock for the rest of this process.

    A CLI command opens the store once and exits; there is no point at which
    releasing early would help, and holding to the end is what stops a second
    process slipping in mid-run. The kernel releases it when the process ends,
    including when it is killed.
    """
    if _LOCK_DEPTH:
        return
    context = store_lock()
    context.__enter__()
    atexit.register(_release_held_lock, context)


def _release_held_lock(context) -> None:
    with contextlib.suppress(Exception):
        context.__exit__(None, None, None)


def restore_login_checked(client, user_id: str, device_id: str, access_token: str):
    """``client.restore_login`` that locks the store and explains what it cannot open.

    Takes the store lock before opening, and keeps it: these are one-shot
    commands, so "until the process exits" is exactly how long the store is in
    use, and the lock is released by the kernel when the last descriptor closes.
    Every path that opens the store therefore holds it, which is what makes
    exclusivity enforced rather than agreed.

    Takes the client as a parameter rather than importing nio, keeping this
    module stdlib-only.
    """
    _hold_store_lock()
    try:
        client.restore_login(
            user_id=user_id, device_id=device_id, access_token=access_token
        )
    except Exception as exc:
        hint = explain_store_error(exc)
        if hint is None:
            raise
        raise SystemExit(f"Error: {hint}") from exc


def store_files_for(user_id: str, device_id: str) -> list[Path]:
    """Every store file belonging to one device.

    nio names them ``{user_id}_{device_id}.<suffix>`` - the database plus the
    blacklisted/ignored/trusted device lists. The trailing dot matters: without
    it a device id that is a prefix of another would collect the other's files
    too.
    """
    prefix = f"{user_id}_{device_id}."
    return sorted(p for p in get_store_path().iterdir() if p.name.startswith(prefix))


def delete_credentials(
    purge_all: bool = False, lock_timeout: float = LOCK_TIMEOUT
) -> list[str]:
    """Remove the stored credentials and the store files of THAT device.

    Returns the names of the files removed, so the caller can say what it did.

    The store directory is shared by every device ever set up here. Globbing
    ``*.db`` and ``*_devices`` across it - which this did - means logging one
    device out destroys the megolm history of all the others. That happened:
    a logout of a broken device took a months-old 25 MB store with it, and only
    a server-side key backup made the rooms readable again.

    ``purge_all`` restores the old sweep for the case where you do want the
    directory emptied. ``backup_key.json`` is never touched either way; it is
    not device-scoped and re-importing keys depends on it.

    The files are removed under the store lock: deleting a store another
    process (the daemon, a send in progress) has open would leave that
    process writing into files that no longer exist. While the lock is held
    elsewhere this waits ``lock_timeout`` seconds and then refuses.
    """
    with store_lock(timeout=lock_timeout):
        return _delete_credentials_locked(purge_all)


def _delete_credentials_locked(purge_all: bool) -> list[str]:
    removed: list[str] = []
    creds = load_credentials()
    creds_path = get_credentials_path()

    if purge_all:
        store_path = get_store_path()
        targets = sorted([*store_path.glob("*.db"), *store_path.glob("*_devices")])
    elif creds and creds.get("user_id") and creds.get("device_id"):
        targets = store_files_for(creds["user_id"], creds["device_id"])
    else:
        # No credentials to scope by. Removing nothing beats removing everything.
        targets = []

    for path in targets:
        path.unlink()
        removed.append(path.name)

    if creds_path.exists():
        creds_path.unlink()
        removed.append(creds_path.name)

    return removed
