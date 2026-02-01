#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["matrix-nio[e2e]"]
# ///
"""Set up E2EE device for Matrix Skill.

This creates a dedicated Matrix device with encryption keys.
Run once to set up E2EE, then matrix-send-e2ee.py works without password.

Requires libolm system library:
    Debian/Ubuntu: sudo apt install libolm-dev
    Fedora:        sudo dnf install libolm-devel
    macOS:         brew install libolm

Usage:
    matrix-e2ee-setup.py PASSWORD
    matrix-e2ee-setup.py --status
    matrix-e2ee-setup.py --logout
    matrix-e2ee-setup.py --help

Arguments:
    PASSWORD    Your Matrix account password (used once, not stored)

Options:
    --status    Check if E2EE device is set up
    --logout    Remove stored device credentials
    --help      Show this help
"""

import asyncio
import json
import sys
import os

# Add script directory to path for _lib imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib import (
    load_config,
    get_store_path,
    load_credentials,
    save_credentials,
    delete_credentials,
)

# Check for libolm before importing nio
try:
    from nio import (
        AsyncClient,
        AsyncClientConfig,
        LoginResponse,
    )
except ImportError as e:
    if "olm" in str(e).lower():
        print("Error: libolm library not found.", file=sys.stderr)
        print("", file=sys.stderr)
        print("Install libolm for your platform:", file=sys.stderr)
        print("  Debian/Ubuntu: sudo apt install libolm-dev", file=sys.stderr)
        print("  Fedora:        sudo dnf install libolm-devel", file=sys.stderr)
        print("  macOS:         brew install libolm", file=sys.stderr)
        sys.exit(1)
    raise


async def setup_device(config: dict, password: str) -> dict:
    """Create a new E2EE device using password login."""
    store_path = get_store_path()

    client_config = AsyncClientConfig(
        store_sync_tokens=True,
        encryption_enabled=True,
    )

    # Extract localpart from user_id for login (some servers require this)
    # @user:server -> user
    user_id = config["user_id"]
    login_user = user_id.split(":")[0].lstrip("@") if user_id.startswith("@") else user_id

    client = AsyncClient(
        homeserver=config["homeserver"],
        user=login_user,
        store_path=str(store_path),
        config=client_config,
    )

    try:
        # Login to create new device with hostname suffix
        import socket
        hostname = socket.gethostname()
        device_name = f"Matrix Skill E2EE @ {hostname}"

        login_response = await client.login(
            password=password,
            device_name=device_name,
        )

        if isinstance(login_response, LoginResponse):
            # Save credentials (password NOT saved)
            save_credentials(
                user_id=login_response.user_id,
                device_id=login_response.device_id,
                access_token=login_response.access_token,
            )
            return {
                "success": True,
                "device_id": login_response.device_id,
                "user_id": login_response.user_id,
            }
        else:
            return {"error": str(login_response)}

    finally:
        await client.close()


def show_status(config: dict):
    """Show current E2EE setup status."""
    creds = load_credentials()

    if creds and creds.get("user_id") == config["user_id"]:
        print("E2EE Status: SET UP")
        print(f"  User:   {creds['user_id']}")
        print(f"  Device: {creds['device_id']}")
        print(f"  Store:  {get_store_path()}")
    else:
        print("E2EE Status: NOT SET UP")
        print("")
        print("Run setup with your Matrix password:")
        print("  matrix-e2ee-setup.py YOUR_PASSWORD")


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Set up E2EE device for Matrix Skill"
    )
    parser.add_argument("password", nargs="?", help="Matrix account password (used once, not stored)")
    parser.add_argument("--status", action="store_true", help="Check E2EE setup status")
    parser.add_argument("--logout", action="store_true", help="Remove stored device credentials")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    config = load_config(require_user_id=True)

    if args.status:
        if args.json:
            creds = load_credentials()
            if creds and creds.get("user_id") == config["user_id"]:
                print(json.dumps({"status": "configured", "device_id": creds["device_id"]}))
            else:
                print(json.dumps({"status": "not_configured"}))
        else:
            show_status(config)
        return

    if args.logout:
        creds = load_credentials()
        if creds:
            delete_credentials()
            if args.json:
                print(json.dumps({"success": True, "message": "Credentials removed"}))
            else:
                print("E2EE device credentials removed.")
                print("Note: The device still exists on the server.")
                print("To fully remove it, go to Element > Settings > Sessions")
        else:
            if args.json:
                print(json.dumps({"success": False, "message": "No credentials found"}))
            else:
                print("No E2EE credentials found.")
        return

    if not args.password:
        # Check if already set up
        creds = load_credentials()
        if creds and creds.get("user_id") == config["user_id"]:
            if args.json:
                print(json.dumps({"status": "already_configured", "device_id": creds["device_id"]}))
            else:
                print("E2EE already set up!")
                print(f"Device: {creds['device_id']}")
        else:
            parser.print_help()
            print("\n" + "="*50)
            print("E2EE device not set up. Provide your Matrix password:")
            print("  matrix-e2ee-setup.py YOUR_PASSWORD")
            sys.exit(1)
        return

    # Check if already set up
    creds = load_credentials()
    if creds and creds.get("user_id") == config["user_id"]:
        if args.json:
            print(json.dumps({"status": "already_configured", "device_id": creds["device_id"]}))
        else:
            print("E2EE already set up!")
            print(f"Device: {creds['device_id']}")
            print("")
            print("To reconfigure, first run: matrix-e2ee-setup.py --logout")
        return

    # Run setup
    result = asyncio.run(setup_device(config, args.password))

    if "error" in result:
        if args.json:
            print(json.dumps(result))
        else:
            print(f"Error: {result['error']}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(result))
    else:
        print("E2EE device created successfully!")
        print(f"  Device ID: {result['device_id']}")
        print(f"  User:      {result['user_id']}")
        print("")
        print("You can now use matrix-send-e2ee.py without password.")
        print("The device appears as 'Matrix Skill E2EE' in your sessions.")


if __name__ == "__main__":
    main()
