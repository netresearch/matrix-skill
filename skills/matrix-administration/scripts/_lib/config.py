# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH

"""Configuration loading for Synapse Admin scripts.

Reuses ``~/.config/matrix/config.json`` (the same file the
``matrix-communication`` skill reads).  Admin scripts require an admin-level
token and accept the following optional fields in addition to the standard
ones:

- ``admin_token``: a Matrix access token for a user with Synapse server-admin
  rights.
- ``admin_token_file``: a file holding that token, so the secret can live
  outside config.json.  ``MATRIX_ADMIN_TOKEN`` in the environment takes
  precedence over both (see ``resolve_tokens``).

Without any of the three, the scripts use the access token of the
matrix-e2ee-cli session (``<data dir>/matrix-e2ee-cli/session.json``, the
device matrix-communication logs in with), which works only when that account
is a server admin.  ``access_token``, ``access_token_file`` and
``MATRIX_ACCESS_TOKEN`` are no longer read.
- ``room_filter``: optional server-suffix filter applied by
  ``synapse-fetch-rooms.py`` (e.g. ``":example.com"``).  Empty/missing means
  no filter.
- ``default_space_id``: optional fallback space ID used by space-related
  scripts when no CLI argument or ``MATRIX_SPACE_ID`` env var is given.

Stdlib only.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# The token the config can carry, with the environment variable that
# overrides it. The two skills share one config file but install
# independently, so nothing here is imported from matrix-communication.
TOKEN_SOURCES = (("admin_token", "MATRIX_ADMIN_TOKEN"),)


class TokenSourceError(ValueError):
    """A configured token file cannot supply a token."""


def get_config_path() -> Path:
    """Return the Matrix configuration file path.

    Respects ``XDG_CONFIG_HOME`` and falls back to ``~/.config``.  Same
    resolution as the matrix-communication skill so a single config file
    is shared by both.
    """
    xdg_config = os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")
    return Path(xdg_config) / "matrix" / "config.json"


def resolve_tokens(config: dict, keys: tuple[str, ...] | None = None) -> dict:
    """Return a copy of ``config`` with each token taken from its strongest source.

    For ``admin_token``, in this order:

    1. ``MATRIX_ADMIN_TOKEN``, when set and not empty;
    2. the file named by ``admin_token_file``, stripped of surrounding
       whitespace; ``~`` is expanded and a relative path is taken relative
       to the directory of config.json;
    3. the ``admin_token`` value in config.json itself.

    Only the tokens named in ``keys`` are resolved (default: all), so a
    broken source of a token the caller never sends cannot stop it; a token
    left out keeps its config.json value.

    Raises TokenSourceError when a configured token file cannot be read or is
    empty. The message names the file, never its content.
    """
    resolved = dict(config)
    for key, env_var in TOKEN_SOURCES:
        if keys is not None and key not in keys:
            continue
        from_env = os.environ.get(env_var, "").strip()
        if from_env:
            resolved[key] = from_env
            continue

        file_name = config.get(f"{key}_file")
        if not file_name:
            continue
        path = Path(file_name).expanduser()
        if not path.is_absolute():
            path = get_config_path().parent / path
        try:
            token = path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise TokenSourceError(
                f"cannot read {key}_file {path}: {exc.strerror or exc}"
            ) from exc
        if not token:
            raise TokenSourceError(f"{key}_file {path} is empty")
        resolved[key] = token
    return resolved


def cli_session_path(env=None) -> Path:
    """matrix-e2ee-cli's session file: $XDG_DATA_HOME, else <home>/.local/share.

    <home> is HOME, else USERPROFILE. The same path as matrix-communication's
    _lib/cutover.cli_session_path, written out here because the skills
    install independently.
    """
    env = os.environ if env is None else env
    data = env.get("XDG_DATA_HOME")
    if not data:
        home = env.get("HOME") or env.get("USERPROFILE")
        if not home:
            raise TokenSourceError(
                "cannot find the matrix-e2ee-cli session: neither XDG_DATA_HOME "
                "nor HOME is set"
            )
        data = Path(home) / ".local" / "share"
    return Path(data) / "matrix-e2ee-cli" / "session.json"


def session_credentials(path: Path) -> tuple[str, str] | None:
    """(access_token, homeserver) of the matrix-e2ee-cli session, or None.

    None when the file does not exist or carries no access token or no
    homeserver. A file
    that exists but cannot be read or parsed raises TokenSourceError.
    """
    try:
        session = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        raise TokenSourceError(
            f"cannot read the matrix-e2ee-cli session {path}: {exc}"
        ) from exc
    if not isinstance(session, dict) or not session.get("access_token"):
        return None
    if not session.get("homeserver"):
        # Its token belongs to its own homeserver only: never pair it with
        # config.json's.
        return None
    return str(session["access_token"]), str(session["homeserver"])


def resolve_admin_token(config: dict) -> tuple[dict, Path | None]:
    """``config`` with ``admin_token`` from its strongest source, and the
    session path when the session was consulted (else None).

    MATRIX_ADMIN_TOKEN, admin_token_file and admin_token first (a set one
    wins, even a dead one), else the matrix-e2ee-cli session, whose token is
    paired with the session's own homeserver. Raises TokenSourceError when a
    token source cannot be used.
    """
    config = resolve_tokens(config, keys=("admin_token",))
    if config.get("admin_token"):
        return config, None
    session_path = cli_session_path()
    credentials = session_credentials(session_path)
    if credentials:
        # The session's token belongs to the session's homeserver.
        config["admin_token"], config["homeserver"] = credentials
    return config, session_path


def load_config(require_admin: bool = True) -> dict:
    """Load Matrix config from ``$XDG_CONFIG_HOME/matrix/config.json``.

    Args:
        require_admin: If True (the default), require an admin token: from
            MATRIX_ADMIN_TOKEN, admin_token_file or admin_token, else the
            access token of the matrix-e2ee-cli session, which is then sent
            to the homeserver recorded in that session.

    Returns:
        Parsed config dict.

    Exits with a helpful message if the config is missing or incomplete.
    """
    config_path = get_config_path()
    if not config_path.exists():
        print(f"Error: Config file not found: {config_path}", file=sys.stderr)
        print("Create it with at least:", file=sys.stderr)
        example = {
            "homeserver": "https://matrix.example.com",
            "admin_token": "syt_...",
        }
        print(json.dumps(example, indent=2), file=sys.stderr)
        sys.exit(1)

    with open(config_path) as f:
        config = json.load(f)
    had_access_token = bool(
        config.get("access_token") or config.get("access_token_file")
    )

    # The config's access_token is matrix-communication's old, second device;
    # it is never sent.
    for key in ("access_token", "access_token_file"):
        config.pop(key, None)

    # Resolve only when the scripts will send a token: a set admin token wins,
    # even a dead one; the session is the fallback. Commands that need no admin
    # credential resolve none, so an unused token source cannot stop them.
    session_path = None
    if require_admin:
        try:
            config, session_path = resolve_admin_token(config)
        except TokenSourceError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)

    if "homeserver" not in config:
        print("Error: config missing required field: homeserver", file=sys.stderr)
        sys.exit(1)

    if require_admin and not config.get("admin_token"):
        print(
            "Error: no admin token. Set MATRIX_ADMIN_TOKEN, 'admin_token_file' or "
            "'admin_token' in config.json to a token of a Synapse server admin, "
            "or log in with matrix-communication's matrix-e2ee-setup.py as a "
            f"server admin (the matrix-e2ee-cli session {session_path} is used "
            "when none of the others is set).",
            file=sys.stderr,
        )
        if had_access_token:
            print(
                "Note: access_token in config.json is no longer read.",
                file=sys.stderr,
            )
        sys.exit(1)

    return config
