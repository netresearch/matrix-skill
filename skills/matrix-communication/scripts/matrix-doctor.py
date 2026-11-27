#!/usr/bin/env -S uv run --script
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Matrix Skill health check and E2EE binary installer.

Checks the matrix-e2ee-cli binary, the configuration and the tokens, and
reports on the E2EE device.

Usage:
    matrix-doctor.py [--install] [--json] [--quiet] [--offline]
    matrix-doctor.py --help

Options:
    --install   Download the pinned matrix-e2ee-cli binary when it is missing
    --json      Output as JSON
    --quiet     Only show errors
    --offline   Skip the homeserver calls (token and e2ee_setup read 'not verified')
    --help      Show this help
"""

import json
import os
import socket
import subprocess
import sys

# Add script directory to path for _lib imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib import cli, cutover, http
from _lib.config import TokenSourceError, get_config_path, resolve_tokens

sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)


def check_e2ee_cli(install: bool = False, offline: bool = False) -> tuple[bool, str]:
    """Check that the pinned matrix-e2ee-cli binary is there and runs.

    Every E2EE script downloads it on first use; ``--install`` does that now, so
    a host without network access later is set up in advance. MATRIX_E2EE_CLI
    names a binary of your own instead (no download, no hash check).
    """
    try:
        path = cli.find_binary()
        if path is None and install and not offline:
            path = cli.ensure_binary(log=cli.stderr_log)
    except (cli.CliError, OSError) as exc:
        return False, f"matrix-e2ee-cli binary unusable: {exc}"
    if path is None:
        try:
            version = cli.load_release()["version"]
        except cli.CliError as exc:
            return False, str(exc)
        return (
            False,
            (
                f"matrix-e2ee-cli {version} not downloaded yet - run matrix-doctor.py "
                "--install (the E2EE scripts also download it on first use)"
            ),
        )
    try:
        result = subprocess.run(  # noqa: PLW1510  # returncode inspected below
            [str(path), "--version"], capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"{path} does not run: {exc}"
    if result.returncode != 0:
        return False, f"{path} --version exited {result.returncode}"
    return True, f"{result.stdout.strip()} ({path})"


def check_config() -> tuple[bool, str, dict]:
    """Check Matrix configuration file."""
    config_path = get_config_path()
    if not config_path.exists():
        return False, f"Config not found at {config_path}", {}

    try:
        with open(config_path) as f:
            config = json.load(f)

        # The scripts take a token from the environment or a token file before
        # the config key; check the token they will actually send.
        try:
            config = resolve_tokens(config)
        except TokenSourceError as e:
            return False, f"Token source unusable: {e}", config

        required = ["homeserver", "user_id"]
        missing = [k for k in required if k not in config]
        if missing:
            return (
                False,
                f"Config missing required fields: {', '.join(missing)}",
                config,
            )

        return True, f"Config OK: {config.get('user_id')}", config
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON in config: {e}", {}
    except Exception as e:  # noqa: BLE001  # intentional fail-soft: error surfaced to caller, not re-raised
        return False, f"Error reading config: {e}", {}


def _verify_credential(
    config: dict, token: str, label: str, remedy: str
) -> tuple[bool | None, str, str | None]:
    """Ask the homeserver whether one credential works.

    Returns ``(state, message, device_id)``. ``state`` is ``True`` when the
    homeserver confirmed the token, ``False`` when it rejected it or it serves a
    different account, and ``None`` when the answer could not be obtained.
    ``device_id`` is only set on ``True`` - it is the device the homeserver
    attributes the token to, which is not necessarily the one the caller expects.

    Delegate to _lib.http.matrix_request rather than hand-rolling urllib: it
    already carries the http(s) scheme allow-list (urllib honours file://, so
    an unguarded homeserver value would turn a health check into a local file
    read), the Matrix error parsing, and the IPv4 retry for hosts with dead
    IPv6 routes. It has no timeout of its own, and a doctor must not hang on a
    black-holed host, so the socket default is scoped around the call.
    """
    request_config = {**config, "access_token": token}
    old_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(5)
    try:
        whoami = http.matrix_request(request_config, "GET", "/account/whoami")
    except ValueError as exc:  # scheme rejected by the allow-list
        return None, str(exc), None
    except Exception as exc:  # noqa: BLE001  # intentional fail-soft: unknown, never reported as OK
        return None, f"Could not verify {label}: {exc}", None
    finally:
        socket.setdefaulttimeout(old_timeout)

    if "error" in whoami:
        errcode = whoami.get("errcode") or ""
        if errcode in ("M_UNKNOWN_TOKEN", "M_MISSING_TOKEN", "M_FORBIDDEN"):
            return (
                False,
                f"{label} rejected by the homeserver ({errcode}) - {remedy}",
                None,
            )
        detail = f"{errcode}: {whoami['error']}" if errcode else str(whoami["error"])
        return None, f"Could not verify {label} - {detail}"[:200], None

    served = whoami.get("user_id", "")
    configured = config.get("user_id", "")
    if configured and served and served != configured:
        return (
            False,
            f"{label} is valid but belongs to {served}, while the config says {configured}",
            None,
        )
    return (
        True,
        f"{label} valid for {served or configured}",
        whoami.get("device_id"),
    )


def check_token(
    config: dict, offline: bool = False, store_ok: bool | None = None
) -> tuple[bool | None, str]:
    """Ask the homeserver whether the config tokens actually work.

    ``check_config`` only proves the file parses. A token that has expired or been
    revoked leaves the config perfectly well-formed, so without this the doctor
    reports a healthy setup while every authenticated call returns HTTP 401
    ``M_UNKNOWN_TOKEN`` - and a green doctor sends you looking for the problem
    everywhere except at the credential.

    Every token in the config is checked, not just the first one found. The two
    serve different scripts - ``synapse-*`` authenticates with ``admin_token``,
    the non-E2EE ``matrix-*.py`` scripts read ``access_token`` - so verifying one
    says nothing about the other.

    Returns ``(True, msg)`` only when the homeserver confirmed every token
    present, ``(False, msg)`` when it rejected any of them, and ``(None, msg)``
    when there is nothing to verify or an answer is missing. Unknown is never OK:
    no token in the config is normal for E2EE use (those scripts authenticate
    from the matrix-e2ee-cli session), and an unreachable homeserver is a missing
    answer, not a passing one.

    ``store_ok`` is ``check_e2ee_setup``'s verdict on the E2EE session, and
    it only changes the *remedy*, never the verdict. A rejected config token
    while the store holds a credential the homeserver confirmed is a stale
    config, not a lost credential: the fix is to repair or drop the config entry,
    and "mint a new token" would send the reader to re-authenticate something
    that is not broken. Reported in the 2026-W36 window as "both Matrix tokens on
    this box are rejected" and parked as a blocker, while a working credential
    sat in the store the whole time.
    """
    tokens = [
        (label, config[label])
        for label in ("admin_token", "access_token")
        if config.get(label)
    ]
    if not tokens:
        return (
            None,
            "No token in config (normal for E2EE - those scripts use the matrix-e2ee-cli session)",
        )

    if not config.get("homeserver"):
        return None, "No homeserver in config - cannot verify the tokens"
    if offline:
        return None, "Not verified (--offline): a parseable token is not a working one"

    if store_ok is True:
        remedy = (
            "the E2EE session holds a credential the homeserver confirmed, so this is a "
            "stale token, not a lost credential - repair or remove it where it is set "
            "(MATRIX_ACCESS_TOKEN / MATRIX_ADMIN_TOKEN, the *_token_file, or "
            "~/.config/matrix/config.json); do not mint a new token, and do not report no access"
        )
    else:
        remedy = (
            "mint a new token for the skill and replace it where it is set "
            "(MATRIX_ACCESS_TOKEN / MATRIX_ADMIN_TOKEN, the *_token_file, or config.json) "
            "- never copy one out of a client you use"
        )

    results = [
        _verify_credential(config, token, label, remedy) for label, token in tokens
    ]
    message = "; ".join(msg for _, msg, _ in results)

    if any(state is False for state, _, _ in results):
        return False, message
    if all(state is True for state, _, _ in results):
        return True, message
    return None, message


def get_session_path():
    """The matrix-e2ee-cli session file (a function, so tests can redirect it)."""
    return cutover.cli_session_path()


def setup_command() -> str:
    """The setup call that mints a device: --force when a session is in the way.

    Without --force, matrix-e2ee-setup.py keeps an existing session and only
    shows its state, so a dead or foreign one needs the flag.
    """
    try:
        exists = get_session_path().exists()
    except cutover.CutoverError:
        exists = False
    return "matrix-e2ee-setup.py --force" if exists else "matrix-e2ee-setup.py"


def token_remedy(e2ee_check: dict) -> str:
    """The quick fix for a rejected config token, decided by the E2EE verdict.

    A working E2EE device makes a dead config token a stale copy to repair;
    --force there would replace a working, verified device. Only a device
    the homeserver rejected (or none at all) is a reason to mint one.
    """
    if e2ee_check.get("ok"):
        return (
            "  - Token rejected: the skill's E2EE device works, so this is a stale "
            "config token - repair or remove it where it is set (MATRIX_ACCESS_TOKEN / "
            "MATRIX_ADMIN_TOKEN, the *_token_file, or config.json): an access_token "
            "can take the device's own token (setup-guide.md, step 6), an admin_token "
            "needs a server-admin token; do not mint a new device"
        )
    if e2ee_check.get("unknown"):
        return (
            "  - Token rejected: the E2EE device could not be checked (see e2ee_setup); "
            "check it before replacing anything - a working device only needs the "
            "config token repaired"
        )
    return (
        "  - Token rejected: mint a new one for the skill "
        f"({setup_command()}), never copy one out of a client you use"
    )


def nio_pending() -> bool:
    """A matrix-nio device of an older version still waits for its takeover."""
    return cutover.pending()


def check_e2ee_setup(config: dict, offline: bool = False) -> tuple[bool | None, str]:
    """Check the E2EE credential - against the homeserver, not just the file.

    Reading matrix-e2ee-cli's ``session.json`` proves a device was set up at some
    point. It does not prove the device still exists: log the device out in
    Element, or delete it from the session list, and the file is unchanged while
    every ``*-e2ee.py`` script starts failing. The failure surfaces as ``Room
    not found`` (a rejected token yields an empty joined-rooms list), which points
    nowhere near the credential - so the file check alone is exactly the trap
    ``check_token`` exists to close, on the credential the E2EE scripts actually
    authenticate with.

    The device comparison also catches the reverse mistake: pasting another
    client's access token into ``session.json``. The token verifies, but it
    belongs to that client's device - and driving one device from two clients
    breaks decryption in both.
    """
    try:
        session_file = get_session_path()
    except cutover.CutoverError as exc:
        return False, f"E2EE session not found: {exc}"

    if not session_file.exists():
        if nio_pending():
            return (
                None,
                (
                    "E2EE device of an older version (matrix-nio) not taken over yet - the "
                    "next E2EE command takes it over (migrate-nio, after a backup of the old "
                    "store)"
                ),
            )
        return (
            False,
            "E2EE not set up (no matrix-e2ee-cli session) - run matrix-e2ee-setup.py",
        )

    try:
        with open(session_file) as f:
            session = json.load(f)
    except Exception as e:  # noqa: BLE001  # intentional fail-soft: error surfaced to caller, not re-raised
        return False, f"Error reading the E2EE session: {e}"

    device_id = session.get("device_id", "unknown")
    token = session.get("access_token")

    if not token:
        return (
            False,
            (
                f"E2EE session for {device_id} carries no access_token - run "
                "matrix-e2ee-setup.py --force"
            ),
        )
    # matrix-e2ee-cli talks to the homeserver recorded in the session, not to
    # config.json's: check the token where it is used.
    config = {
        **config,
        "homeserver": session.get("homeserver") or config.get("homeserver"),
    }
    if not config.get("homeserver"):
        return None, f"E2EE device {device_id} configured - no homeserver to verify it"
    if offline:
        return None, f"E2EE device {device_id} configured - not verified (--offline)"

    state, message, served_device = _verify_credential(
        config,
        token,
        f"E2EE credential ({device_id})",
        "the device is gone - run matrix-e2ee-setup.py --force to mint a new one, "
        "then matrix-key-backup.py --import-keys to restore the room keys",
    )
    if state is not True:
        return state, message

    if served_device and served_device != device_id:
        return (
            False,
            (
                f"E2EE credential belongs to device {served_device}, but session.json "
                f"says {device_id} - this is another client's token; run "
                "matrix-e2ee-setup.py --force for a device of your own"
            ),
        )

    return True, f"E2EE device confirmed by the homeserver: {device_id}"


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Matrix Skill health check and setup")
    parser.add_argument(
        "--install",
        action="store_true",
        help="Download the pinned matrix-e2ee-cli binary when it is missing",
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--quiet", "-q", action="store_true", help="Only show errors")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Skip the homeserver calls; the token and E2EE checks then report 'not verified', never OK",
    )

    args = parser.parse_args()

    checks = {
        # Not critical: the non-E2EE scripts work without it, and every E2EE
        # script downloads it on first use.
        "e2ee_cli": {"ok": False, "message": "", "critical": False},
        "config": {"ok": False, "message": "", "critical": True},
        "token": {"ok": False, "message": "", "critical": False},
        "e2ee_setup": {"ok": False, "message": "", "critical": False},
    }

    # Check the E2EE binary (downloaded with --install)
    cli_ok, cli_msg = check_e2ee_cli(install=args.install, offline=args.offline)
    checks["e2ee_cli"]["ok"] = cli_ok
    checks["e2ee_cli"]["message"] = cli_msg

    # Check config
    config_ok, config_msg, config_data = check_config()
    checks["config"]["ok"] = config_ok
    checks["config"]["message"] = config_msg

    # E2EE first, because its verdict changes the advice the token check gives.
    # The two credentials are independent, but the *remedy* is not: a rejected
    # config token while the store holds a working one is a stale config, and
    # telling the reader to mint a new token there sends them to re-authenticate
    # something that is not broken.
    e2ee_ok, e2ee_msg = check_e2ee_setup(config_data, offline=args.offline)
    checks["e2ee_setup"]["ok"] = e2ee_ok is True
    checks["e2ee_setup"]["unknown"] = e2ee_ok is None
    checks["e2ee_setup"]["message"] = e2ee_msg

    # Check the token against the homeserver (a parseable token is not a working one)
    token_ok, token_msg = check_token(
        config_data, offline=args.offline, store_ok=e2ee_ok
    )
    checks["token"]["ok"] = token_ok is True
    checks["token"]["unknown"] = token_ok is None
    checks["token"]["message"] = token_msg

    # Output
    if args.json:
        print(json.dumps(checks, indent=2))
        sys.exit(0 if all(c["ok"] for c in checks.values() if c.get("critical")) else 1)

    # Pretty output
    all_ok = True
    critical_ok = True

    if not args.quiet:
        print("=" * 60)
        print("Matrix Skill Health Check")
        print("=" * 60)
        print()

    unverified = []

    for name, check in checks.items():
        # Three states, not two: a check that could not be answered must not
        # render as OK (it would claim a verification that never happened) and
        # must not render as FAIL either (it is not a finding).
        if check.get("unknown"):
            icon = "??"
            unverified.append(name)
        else:
            icon = "OK" if check["ok"] else "FAIL"
        critical = " (required)" if check.get("critical") else ""

        if not check["ok"] and not check.get("unknown"):
            all_ok = False
            if check.get("critical"):
                critical_ok = False

        if not args.quiet or not check["ok"]:
            print(f"[{icon}] {name}{critical}")
            print(f"     {check['message']}")
            print()

    # Summary
    if not args.quiet:
        print("=" * 60)

    if all_ok and not unverified:
        print("All checks passed! Matrix Skill is ready to use.")
    elif all_ok:
        print(
            f"Checks passed, except {', '.join(unverified)} - could not be verified (see above)."
        )
    elif critical_ok:
        print("Core functionality OK. Some optional features may be limited.")
    else:
        print("Some required checks failed. See above for details.")
        print()
        print("Quick fix:")
        if not checks["e2ee_cli"]["ok"]:
            print("  - Run: matrix-doctor.py --install")
        if not checks["config"]["ok"]:
            print("  - Set up Matrix: see SKILL.md Setup Guide")
        if (
            not checks["e2ee_setup"]["ok"]
            and not checks["e2ee_setup"].get("unknown")
            and checks["config"]["ok"]
        ):
            print(f"  - Run: {setup_command()}")
        if not checks["token"]["ok"] and not checks["token"].get("unknown"):
            print(token_remedy(checks["e2ee_setup"]))

    sys.exit(0 if critical_ok else 1)


if __name__ == "__main__":
    main()
