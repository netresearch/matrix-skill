# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH

"""Configuration loading for Synapse Admin scripts.

Reuses ``~/.config/matrix/config.json`` (the same file the
``matrix-communication`` skill reads).  Admin scripts require an admin-level
token and accept the following optional fields in addition to the standard
ones:

- ``admin_token``: a Matrix access token for a user with Synapse server-admin
  rights.  Falls back to ``access_token`` if absent.
- ``admin_token_file`` / ``access_token_file``: a file holding that token, so
  the secret can live outside config.json.  ``MATRIX_ADMIN_TOKEN`` and
  ``MATRIX_ACCESS_TOKEN`` in the environment take precedence over both (see
  ``resolve_tokens``).
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

# Each token the config can carry, with the environment variable that
# overrides it. Kept identical to matrix-communication's _lib/config.py: the
# two skills share one config file but install independently.
TOKEN_SOURCES = (
    ("admin_token", "MATRIX_ADMIN_TOKEN"),
    ("access_token", "MATRIX_ACCESS_TOKEN"),
)


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

    For ``admin_token`` and ``access_token``, in this order:

    1. the environment variable (``MATRIX_ADMIN_TOKEN``, ``MATRIX_ACCESS_TOKEN``),
       when set and not empty;
    2. the file named by ``admin_token_file`` / ``access_token_file``, stripped
       of surrounding whitespace; ``~`` is expanded and a relative path is
       taken relative to the directory of config.json;
    3. the ``admin_token`` / ``access_token`` value in config.json itself.

    Only the tokens named in ``keys`` are resolved (default: both), so a
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


def load_config(require_admin: bool = True) -> dict:
    """Load Matrix config from ``$XDG_CONFIG_HOME/matrix/config.json``.

    Args:
        require_admin: If True (the default), require an admin token to be
            present (either as ``admin_token`` or ``access_token``).

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

    # Resolve only the token the scripts will send: admin_token wins when it
    # yields one, access_token is the fallback, and commands that need no
    # admin credential resolve none, so an unused token source cannot stop them.
    if require_admin:
        try:
            config = resolve_tokens(config, keys=("admin_token",))
            if not config.get("admin_token"):
                config = resolve_tokens(config, keys=("access_token",))
        except TokenSourceError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)

    if "homeserver" not in config:
        print("Error: config missing required field: homeserver", file=sys.stderr)
        sys.exit(1)

    if require_admin and not (config.get("admin_token") or config.get("access_token")):
        print(
            "Error: config missing admin token. Set 'admin_token' (preferred) "
            "or 'access_token' to a token belonging to a Synapse server admin, "
            "or supply it through MATRIX_ADMIN_TOKEN or 'admin_token_file'.",
            file=sys.stderr,
        )
        sys.exit(1)

    return config
