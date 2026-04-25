"""Configuration loading for Synapse Admin scripts.

Reuses ``~/.config/matrix/config.json`` (the same file the
``matrix-communication`` skill reads).  Admin scripts require an admin-level
token and accept the following optional fields in addition to the standard
ones:

- ``admin_token``: a Matrix access token for a user with Synapse server-admin
  rights.  Falls back to ``access_token`` if absent.
- ``room_filter``: optional server-suffix filter applied by
  ``synapse-fetch-rooms.py`` (e.g. ``":example.com"``).  Empty/missing means
  no filter.
- ``default_space_id``: optional fallback space ID used by space-related
  scripts when no CLI argument or ``MATRIX_SPACE_ID`` env var is given.

Stdlib only.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def load_config(require_admin: bool = True) -> dict:
    """Load Matrix config from ``~/.config/matrix/config.json``.

    Args:
        require_admin: If True (the default), require an admin token to be
            present (either as ``admin_token`` or ``access_token``).

    Returns:
        Parsed config dict.

    Exits with a helpful message if the config is missing or incomplete.
    """
    config_path = Path.home() / ".config" / "matrix" / "config.json"
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

    if "homeserver" not in config:
        print("Error: config missing required field: homeserver", file=sys.stderr)
        sys.exit(1)

    if require_admin and not (config.get("admin_token") or config.get("access_token")):
        print(
            "Error: config missing admin token. Set 'admin_token' (preferred) "
            "or 'access_token' to a token belonging to a Synapse server admin.",
            file=sys.stderr,
        )
        sys.exit(1)

    return config
