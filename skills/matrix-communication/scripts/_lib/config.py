# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH

"""Configuration loading for Matrix scripts.

All functions use ONLY stdlib.
"""

import json
import os
import sys
from pathlib import Path

# Each token the config can carry, with the environment variable that
# overrides it. A token may also come from a file named by ``<key>_file``, so
# the secret can live outside config.json and be rotated without touching it.
TOKEN_SOURCES = (
    ("admin_token", "MATRIX_ADMIN_TOKEN"),
    ("access_token", "MATRIX_ACCESS_TOKEN"),
)


class TokenSourceError(ValueError):
    """A configured token file cannot supply a token."""


def get_config_path() -> Path:
    """Get the Matrix configuration file path.

    Returns ~/.config/matrix/config.json (respects XDG_CONFIG_HOME if set).
    """
    xdg_config = os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")
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


def load_config(require_user_id: bool = False) -> dict:
    """Load Matrix config from ~/.config/matrix/config.json.

    Tokens are resolved with ``resolve_tokens``, so ``access_token`` may come
    from ``MATRIX_ACCESS_TOKEN`` or ``access_token_file`` instead of the file.

    Args:
        require_user_id: If True, require user_id field (for E2EE scripts)

    Returns:
        dict with homeserver, access_token, and optionally user_id, bot_prefix

    Exits with error if config not found or missing required fields.
    """
    config_path = get_config_path()
    if not config_path.exists():
        print(f"Error: Config file not found: {config_path}", file=sys.stderr)
        print("Create it with:", file=sys.stderr)
        example = {
            "homeserver": "https://matrix.org",
            "access_token": "syt_...",
        }
        if require_user_id:
            example["user_id"] = "@user:matrix.org"
        print(json.dumps(example, indent=2), file=sys.stderr)
        sys.exit(1)

    with open(config_path) as f:
        config = json.load(f)

    try:
        # Only the access token: these scripts never send the admin token.
        config = resolve_tokens(config, keys=("access_token",))
    except TokenSourceError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    # Validate required fields
    required = ["homeserver"]
    if require_user_id:
        required.append("user_id")
    else:
        required.append("access_token")

    missing = [f for f in required if f not in config]
    if missing:
        print(
            f"Error: Config missing required fields: {', '.join(missing)}",
            file=sys.stderr,
        )
        if "access_token" in missing:
            print(
                "The access token can also come from MATRIX_ACCESS_TOKEN or "
                "from a file named by access_token_file.",
                file=sys.stderr,
            )
        sys.exit(1)

    return config
