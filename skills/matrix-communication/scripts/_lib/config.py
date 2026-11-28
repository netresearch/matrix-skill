# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH

"""Configuration lookup for Matrix scripts.

All functions use ONLY stdlib. The scripts of this skill authenticate with the
matrix-e2ee-cli session only; the CLI reads config.json itself. What is left
here serves matrix-doctor.py: the config path, and the admin token of
matrix-administration, which the doctor verifies.
"""

import os
from pathlib import Path

# The token the config can carry, with the environment variable that
# overrides it. A token may also come from a file named by ``<key>_file``, so
# the secret can live outside config.json and be rotated without touching it.
# access_token is not among them: no script sends it any more.
TOKEN_SOURCES = (("admin_token", "MATRIX_ADMIN_TOKEN"),)


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
