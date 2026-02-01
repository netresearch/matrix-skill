"""E2EE credential management for Matrix scripts.

All functions use ONLY stdlib - no nio dependencies here.
The actual E2EE functionality (using nio) is in the scripts themselves.
"""

import json
import os
from pathlib import Path


def get_store_path() -> Path:
    """Get or create the E2EE key store directory.

    Uses XDG_DATA_HOME or falls back to ~/.local/share/matrix-skill/store
    """
    xdg_data = os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")
    store_path = Path(xdg_data) / "matrix-skill" / "store"
    store_path.mkdir(parents=True, exist_ok=True)
    return store_path


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

    Credentials file is chmod 600 for security.
    """
    creds_path = get_credentials_path()
    with open(creds_path, "w") as f:
        json.dump({
            "user_id": user_id,
            "device_id": device_id,
            "access_token": access_token,
        }, f, indent=2)
    os.chmod(creds_path, 0o600)


def delete_credentials():
    """Remove stored device credentials and key store files."""
    creds_path = get_credentials_path()
    if creds_path.exists():
        creds_path.unlink()

    # Also remove key store databases
    store_path = get_store_path()
    for db_file in store_path.glob("*.db"):
        db_file.unlink()
    for key_file in store_path.glob("*_devices"):
        key_file.unlink()
