"""Configuration loading for Matrix scripts.

All functions use ONLY stdlib.
"""

import json
import sys
from pathlib import Path


def load_config(require_user_id: bool = False) -> dict:
    """Load Matrix config from ~/.config/matrix/config.json.

    Args:
        require_user_id: If True, require user_id field (for E2EE scripts)

    Returns:
        dict with homeserver, access_token, and optionally user_id, bot_prefix

    Exits with error if config not found or missing required fields.
    """
    config_path = Path.home() / ".config" / "matrix" / "config.json"
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

    # Validate required fields
    required = ["homeserver"]
    if require_user_id:
        required.append("user_id")
    else:
        required.append("access_token")

    missing = [f for f in required if f not in config]
    if missing:
        print(f"Error: Config missing required fields: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    return config
