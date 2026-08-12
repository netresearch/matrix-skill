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
        json.dump(
            {
                "user_id": user_id,
                "device_id": device_id,
                "access_token": access_token,
            },
            f,
            indent=2,
        )
    os.chmod(creds_path, 0o600)


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
        "Run every script on the same pin. If the pin has moved, the store has to "
        "be recreated - it cannot be migrated:\n"
        "  matrix-e2ee-setup.py --logout && matrix-e2ee-setup.py\n"
        "  matrix-key-backup.py --import-keys\n"
        "  matrix-e2ee-verify.py --request DEVICE"
    )


def restore_login_checked(client, user_id: str, device_id: str, access_token: str):
    """``client.restore_login`` that explains a store it cannot open.

    Takes the client as a parameter rather than importing nio, keeping this
    module stdlib-only.
    """
    try:
        client.restore_login(
            user_id=user_id, device_id=device_id, access_token=access_token
        )
    except Exception as exc:
        hint = explain_store_error(exc)
        if hint is None:
            raise
        raise SystemExit(f"Error: {hint}") from exc


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
