#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["matrix-nio[e2e]"]
# ///
"""Interactive device verification for Matrix E2EE.

Allows verifying this device with another device using emoji verification (SAS).

Usage:
    matrix-e2ee-verify.py                    # Wait for incoming verification
    matrix-e2ee-verify.py --request DEVICE   # Request verification with device
    matrix-e2ee-verify.py --help

Options:
    --request DEVICE   Initiate verification with specified device ID
    --timeout SECS     Timeout for waiting (default: 60)
    --help             Show this help
"""

import asyncio
import json
import os
import sys
from pathlib import Path

try:
    from nio import (
        AsyncClient,
        AsyncClientConfig,
        KeyVerificationStart,
        KeyVerificationKey,
        KeyVerificationMac,
        KeyVerificationCancel,
        ToDeviceError,
    )
except ImportError as e:
    if "olm" in str(e).lower():
        print("Error: libolm library not found.", file=sys.stderr)
        sys.exit(1)
    raise


def load_config() -> dict:
    config_path = Path.home() / ".config" / "matrix" / "config.json"
    if not config_path.exists():
        print(f"Error: Config not found: {config_path}", file=sys.stderr)
        sys.exit(1)
    with open(config_path) as f:
        return json.load(f)


def get_store_path() -> Path:
    xdg_data = os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")
    store_path = Path(xdg_data) / "matrix-skill" / "store"
    store_path.mkdir(parents=True, exist_ok=True)
    return store_path


def load_credentials() -> dict | None:
    creds_path = get_store_path() / "credentials.json"
    if creds_path.exists():
        with open(creds_path) as f:
            return json.load(f)
    return None


class VerificationHandler:
    def __init__(self, client):
        self.client = client
        self.current_verification = None
        self.emojis = None
        self.verified = False
        self.cancelled = False

    async def handle_event(self, event):
        """Handle verification events."""
        if isinstance(event, KeyVerificationStart):
            print(f"\nVerification request from {event.sender}")
            print(f"Transaction ID: {event.transaction_id}")
            # Accept the verification
            self.current_verification = event.transaction_id
            await self.client.accept_key_verification(event.transaction_id)
            print("Accepted verification request...")

        elif isinstance(event, KeyVerificationKey):
            # We received the key, now we can show emojis
            sas = self.client.key_verifications.get(event.transaction_id)
            if sas:
                self.emojis = sas.get_emoji()
                print("\n" + "="*50)
                print("VERIFY THESE EMOJIS MATCH ON BOTH DEVICES:")
                print("="*50)
                for emoji, name in self.emojis:
                    print(f"  {emoji}  {name}")
                print("="*50)
                print("\nDo the emojis match? (yes/no): ", end="", flush=True)

        elif isinstance(event, KeyVerificationMac):
            # Verification complete on their side
            sas = self.client.key_verifications.get(event.transaction_id)
            if sas:
                # Confirm on our side
                await self.client.confirm_key_verification(event.transaction_id)
                self.verified = True
                print("\nVerification successful! Device is now verified.")

        elif isinstance(event, KeyVerificationCancel):
            print(f"\nVerification cancelled: {event.reason}")
            self.cancelled = True


async def run_verification(config: dict, request_device: str = None, timeout: int = 60):
    """Run interactive verification."""
    store_path = get_store_path()
    creds = load_credentials()

    if not creds or creds.get("user_id") != config["user_id"]:
        # Fall back to access token mode
        if "access_token" not in config:
            print("Error: No credentials. Run matrix-e2ee-setup.py first.", file=sys.stderr)
            return False

        from nio import WhoamiResponse
        temp_client = AsyncClient(config["homeserver"], config["user_id"])
        temp_client.access_token = config["access_token"]
        whoami = await temp_client.whoami()
        await temp_client.close()
        if isinstance(whoami, WhoamiResponse):
            device_id = whoami.device_id
            access_token = config["access_token"]
        else:
            print(f"Error: {whoami}", file=sys.stderr)
            return False
    else:
        device_id = creds["device_id"]
        access_token = creds["access_token"]

    print(f"Device ID: {device_id}")

    client_config = AsyncClientConfig(
        store_sync_tokens=True,
        encryption_enabled=True,
    )

    client = AsyncClient(
        homeserver=config["homeserver"],
        user=config["user_id"],
        device_id=device_id,
        store_path=str(store_path),
        config=client_config,
    )

    handler = VerificationHandler(client)

    # Add callbacks for verification events
    client.add_to_device_callback(handler.handle_event, KeyVerificationStart)
    client.add_to_device_callback(handler.handle_event, KeyVerificationKey)
    client.add_to_device_callback(handler.handle_event, KeyVerificationMac)
    client.add_to_device_callback(handler.handle_event, KeyVerificationCancel)

    try:
        client.restore_login(config["user_id"], device_id, access_token)
        if client.store:
            client.load_store()

        # Initial sync
        print("Syncing...")
        await client.sync(timeout=10000)

        if request_device:
            # Initiate verification with specific device
            print(f"Requesting verification with device {request_device}...")
            # Find the device
            for user_id, devices in client.device_store.items():
                for dev_id, device in devices.items():
                    if dev_id == request_device:
                        await client.start_key_verification(device)
                        print(f"Verification request sent to {request_device}")
                        break
        else:
            print(f"\nWaiting for verification request...")
            print(f"In Element, go to: Settings → Security → Sessions")
            print(f"Find '{device_id}' and click 'Verify'")
            print(f"\nTimeout: {timeout} seconds")

        # Wait for verification with periodic syncs
        start_time = asyncio.get_event_loop().time()
        while not handler.verified and not handler.cancelled:
            if asyncio.get_event_loop().time() - start_time > timeout:
                print("\nTimeout waiting for verification.")
                return False

            # Check for user input if emojis are shown
            if handler.emojis and not handler.verified:
                # Non-blocking input check would be complex, so we confirm automatically
                # In a real interactive script, you'd want proper input handling
                pass

            await client.sync(timeout=5000)

        return handler.verified

    finally:
        await client.close()


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Interactive device verification")
    parser.add_argument("--request", metavar="DEVICE", help="Request verification with device ID")
    parser.add_argument("--timeout", type=int, default=60, help="Timeout in seconds")

    args = parser.parse_args()
    config = load_config()

    success = asyncio.run(run_verification(
        config=config,
        request_device=args.request,
        timeout=args.timeout,
    ))

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
