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
    matrix-e2ee-verify.py --list             # List your devices
    matrix-e2ee-verify.py --help

Options:
    --request DEVICE   Initiate verification with specified device ID
    --list             List all your devices
    --timeout SECS     Timeout for waiting (default: 60)
    --debug            Enable debug output
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
        KeyVerificationEvent,
        KeyVerificationStart,
        KeyVerificationAccept,
        KeyVerificationKey,
        KeyVerificationMac,
        KeyVerificationCancel,
        ToDeviceMessage,
        ToDeviceError,
        DevicesResponse,
    )
    # Try to import newer verification events (may not exist in older nio)
    try:
        from nio import KeyVerificationRequest
    except ImportError:
        KeyVerificationRequest = None
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
    def __init__(self, client, debug=False):
        self.client = client
        self.debug = debug
        self.current_verification = None
        self.emojis = None
        self.verified = False
        self.cancelled = False
        self.emoji_confirmed = False

    def _debug(self, msg):
        if self.debug:
            print(f"[DEBUG] {msg}")

    async def handle_event(self, event):
        """Handle verification events."""
        event_type = type(event).__name__
        self._debug(f"Received {event_type} from {event.sender}")
        if hasattr(event, 'transaction_id'):
            self._debug(f"Transaction ID: {event.transaction_id}")

        # Handle KeyVerificationRequest (initial request to verify)
        if KeyVerificationRequest and isinstance(event, KeyVerificationRequest):
            print(f"\nVerification request from {event.sender}")
            self.current_verification = event.transaction_id
            try:
                await self.client.accept_key_verification(event.transaction_id)
                print("Accepted, waiting for key exchange...")
            except Exception as e:
                self._debug(f"Error accepting request: {e}")

        elif isinstance(event, KeyVerificationStart):
            print(f"\nVerification started")
            self.current_verification = event.transaction_id
            try:
                await self.client.accept_key_verification(event.transaction_id)
                print("Accepted, waiting for key exchange...")
            except Exception as e:
                self._debug(f"Error accepting: {e}")

        elif isinstance(event, KeyVerificationAccept):
            print(f"\nVerification accepted by other device")
            self._debug(f"Method: {event.method if hasattr(event, 'method') else 'unknown'}")

        elif isinstance(event, KeyVerificationKey):
            if self.emoji_confirmed:
                self._debug("Already confirmed, ignoring duplicate KeyVerificationKey")
                return

            sas = self.client.key_verifications.get(event.transaction_id)
            if sas:
                try:
                    self.emojis = sas.get_emoji()
                    print("\n" + "="*50)
                    print("VERIFY THESE EMOJIS MATCH ON BOTH DEVICES:")
                    print("="*50)
                    for emoji, name in self.emojis:
                        print(f"  {emoji}  {name}")
                    print("="*50)

                    # Confirm the short auth string (emojis match)
                    # This also sends our MAC
                    print("\nConfirming emojis match...")
                    await self.client.confirm_short_auth_string(event.transaction_id)
                    self.emoji_confirmed = True
                    print("Confirmed! Waiting for other device to confirm...")
                except Exception as e:
                    self._debug(f"Error in key verification: {e}")
            else:
                self._debug(f"No SAS for transaction {event.transaction_id}")

        elif isinstance(event, KeyVerificationMac):
            sas = self.client.key_verifications.get(event.transaction_id)
            if sas:
                try:
                    await self.client.confirm_key_verification(event.transaction_id)
                    self.verified = True
                    print("\n✓ Verification successful! Device is now verified.")
                except Exception as e:
                    self._debug(f"Error confirming: {e}")
            else:
                self._debug("No SAS for MAC verification")

        elif isinstance(event, KeyVerificationCancel):
            if self.current_verification == event.transaction_id:
                print(f"\nVerification cancelled: {event.reason}")
                self.cancelled = True
            else:
                self._debug(f"Ignoring cancel for old transaction")

        else:
            self._debug(f"Unhandled event type: {event_type}")


async def run_verification(config: dict, request_device: str = None, timeout: int = 60, debug: bool = False):
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

    handler = VerificationHandler(client, debug=debug)

    # Add callbacks for verification events
    # Use base class to catch ALL verification events
    client.add_to_device_callback(handler.handle_event, KeyVerificationEvent)
    # Also register specific types for compatibility
    if KeyVerificationRequest:
        client.add_to_device_callback(handler.handle_event, KeyVerificationRequest)
    client.add_to_device_callback(handler.handle_event, KeyVerificationStart)
    client.add_to_device_callback(handler.handle_event, KeyVerificationAccept)
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

        if debug:
            print(f"[DEBUG] Active verifications: {list(client.key_verifications.keys())}")

        if request_device:
            # Initiate verification with specific device by sending to-device message
            print(f"Requesting verification with device {request_device}...")

            import secrets
            import time
            txn_id = secrets.token_hex(16)
            handler.current_verification = txn_id

            # Send m.key.verification.request
            request_content = {
                "from_device": device_id,
                "transaction_id": txn_id,
                "methods": ["m.sas.v1"],
                "timestamp": int(time.time() * 1000),
            }

            msg = ToDeviceMessage(
                type="m.key.verification.request",
                recipient=config["user_id"],
                recipient_device=request_device,
                content=request_content,
            )

            resp = await client.to_device(msg)
            if isinstance(resp, ToDeviceError):
                print(f"Error sending request: {resp}", file=sys.stderr)
                return False

            print(f"Verification request sent!")
            print(f"Transaction ID: {txn_id}")
            print(f"\nCheck Element for verification popup on device {request_device}")
            print(f"Accept the verification request there.")
        else:
            print(f"\nWaiting for verification request...")
            print(f"In Element, go to: Settings → Security → Sessions")
            print(f"Find '{device_id}' and click 'Verify'")
            print(f"\nTimeout: {timeout} seconds")

        # Wait for verification with periodic syncs
        start_time = asyncio.get_event_loop().time()
        sync_count = 0
        while not handler.verified and not handler.cancelled:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout:
                print("\nTimeout waiting for verification.")
                return False

            sync_count += 1
            if sync_count % 12 == 0:  # Every ~60 seconds
                print(f"Still waiting... ({int(elapsed)}s elapsed)")

            await client.sync(timeout=5000)

        return handler.verified

    finally:
        await client.close()


async def list_devices(config: dict) -> list:
    """List all devices for the current user."""
    store_path = get_store_path()
    creds = load_credentials()

    if creds and creds.get("user_id") == config["user_id"]:
        device_id = creds["device_id"]
        access_token = creds["access_token"]
    elif "access_token" in config:
        access_token = config["access_token"]
        from nio import WhoamiResponse
        temp_client = AsyncClient(config["homeserver"], config["user_id"])
        temp_client.access_token = access_token
        whoami = await temp_client.whoami()
        await temp_client.close()
        if isinstance(whoami, WhoamiResponse):
            device_id = whoami.device_id
        else:
            return []
    else:
        return []

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

    try:
        client.restore_login(config["user_id"], device_id, access_token)

        resp = await client.devices()
        if isinstance(resp, DevicesResponse):
            devices = []
            for d in resp.devices:
                devices.append({
                    "device_id": d.id,
                    "display_name": d.display_name or "No name",
                    "is_current": d.id == device_id,
                })
            return devices
        return []
    finally:
        await client.close()


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Interactive device verification")
    parser.add_argument("--request", metavar="DEVICE", help="Request verification with device ID")
    parser.add_argument("--list", action="store_true", help="List all your devices")
    parser.add_argument("--timeout", type=int, default=60, help="Timeout in seconds")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")

    args = parser.parse_args()
    config = load_config()

    if args.list:
        devices = asyncio.run(list_devices(config))
        if not devices:
            print("No devices found or error getting devices")
            sys.exit(1)

        print("Your devices:")
        for d in devices:
            current = " (this device)" if d["is_current"] else ""
            print(f"  {d['device_id']}: {d['display_name']}{current}")
        sys.exit(0)

    success = asyncio.run(run_verification(
        config=config,
        request_device=args.request,
        timeout=args.timeout,
        debug=args.debug,
    ))

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
