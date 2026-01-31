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
        ToDeviceEvent,
        UnknownToDeviceEvent,
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
        self.key_sent = False
        self.sas_accepted = False

    def _debug(self, msg):
        if self.debug:
            print(f"[DEBUG] {msg}")

    async def handle_raw_event(self, event):
        """Handle raw to-device events including unknown verification events."""
        # Check for m.key.verification.request (not natively supported by nio)
        if isinstance(event, UnknownToDeviceEvent) and hasattr(event, 'source'):
            source = event.source

            if source.get('type') == 'm.key.verification.request':
                content = source.get('content', {})
                txn_id = content.get('transaction_id')
                from_device = content.get('from_device')
                methods = content.get('methods', [])
                sender = source.get('sender')

                print(f"\nVerification request received!")
                print(f"  From: {sender} / {from_device}")
                print(f"  Methods: {methods}")

                if 'm.sas.v1' in methods:
                    # Respond with m.key.verification.ready
                    self.current_verification = txn_id
                    self._debug(f"Sending ready response for {txn_id}")

                    ready_content = {
                        "from_device": self.client.device_id,
                        "transaction_id": txn_id,
                        "methods": ["m.sas.v1"],
                    }

                    msg = ToDeviceMessage(
                        type="m.key.verification.ready",
                        recipient=sender,
                        recipient_device=from_device,
                        content=ready_content,
                    )

                    resp = await self.client.to_device(msg)
                    self._debug(f"Ready response sent: {type(resp).__name__}")
                    print("Ready sent, waiting for Element to start verification...")
                else:
                    print(f"Unsupported methods: {methods}")

            elif source.get('type') == 'm.key.verification.start':
                content = source.get('content', {})
                txn_id = content.get('transaction_id')
                from_device = content.get('from_device')
                method = content.get('method')
                sender = source.get('sender')

                print(f"\nVerification START received (as unknown event)!")
                print(f"  Method: {method}")
                self.current_verification = txn_id

                # TODO: Handle start manually if nio doesn't pick it up

            elif source.get('type', '').startswith('m.key.verification.'):
                self._debug(f"Other verification event: {source.get('type')}")

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
                print("Accepted request, waiting for start...")
            except Exception as e:
                self._debug(f"Error accepting request: {e}")

        elif isinstance(event, KeyVerificationStart):
            if self.sas_accepted:
                self._debug("Already accepted start, ignoring duplicate")
                return
            print(f"\nVerification started (method: {event.method})")
            self.current_verification = event.transaction_id
            try:
                resp = await self.client.accept_key_verification(event.transaction_id)
                self._debug(f"Accept response: {type(resp).__name__}")
                self.sas_accepted = True
                print("Accepted, waiting for key exchange...")
            except Exception as e:
                self._debug(f"Error accepting: {e}")

        elif isinstance(event, KeyVerificationAccept):
            print(f"\nOther device accepted verification")
            self._debug(f"Commitment: {event.commitment if hasattr(event, 'commitment') else 'N/A'}")

        elif isinstance(event, KeyVerificationKey):
            if self.key_sent:
                self._debug("Already processed key event, ignoring duplicate")
                return

            sas = self.client.key_verifications.get(event.transaction_id)
            if not sas:
                self._debug(f"No SAS for transaction {event.transaction_id}")
                self._debug(f"Active verifications: {list(self.client.key_verifications.keys())}")
                return

            try:
                self._debug(f"SAS state - their key set: {sas.other_key_set}")

                # Get emojis (requires both keys)
                self.emojis = sas.get_emoji()
                print("\n" + "="*50)
                print("VERIFY THESE EMOJIS MATCH ON BOTH DEVICES:")
                print("="*50)
                for emoji, name in self.emojis:
                    print(f"  {emoji}  {name}")
                print("="*50)

                # Send our key if not already sent
                if not self.key_sent:
                    self._debug("Sending our key...")
                    key_msg = sas.share_key()
                    if key_msg:
                        await self.client.to_device(key_msg)
                        self._debug("Key sent")
                    self.key_sent = True

                # Accept the SAS (user confirms emojis match)
                print("\nConfirming emojis match...")
                sas.accept_sas()
                self._debug("SAS accepted")

                # Now send our MAC
                mac_msg = sas.get_mac()
                if mac_msg:
                    await self.client.to_device(mac_msg)
                    self._debug("MAC sent")
                print("Waiting for other device to confirm...")

            except Exception as e:
                self._debug(f"Error in key verification: {e}")
                import traceback
                self._debug(traceback.format_exc())

        elif isinstance(event, KeyVerificationMac):
            if self.verified:
                self._debug("Already verified, ignoring duplicate MAC")
                return

            self._debug("Received MAC from other device")
            sas = self.client.key_verifications.get(event.transaction_id)
            if sas:
                try:
                    self._debug(f"SAS verified state before: {sas.verified}")

                    # Verify their MAC
                    verified = sas.receive_mac_event(event)
                    self._debug(f"MAC verification result: {verified}")
                    self._debug(f"SAS verified state after: {sas.verified}")

                    if sas.verified:
                        self.verified = True
                        print("\n✓ Verification successful!")

                        # Send m.key.verification.done to complete the flow
                        self._debug("Sending done message...")
                        done_content = {
                            "transaction_id": event.transaction_id,
                        }

                        done_msg = ToDeviceMessage(
                            type="m.key.verification.done",
                            recipient=event.sender,
                            recipient_device=sas.other_device_id if hasattr(sas, 'other_device_id') else sas.other_olm_device.device_id,
                            content=done_content,
                        )

                        await self.client.to_device(done_msg)
                        self._debug("Done message sent")
                        print("Device is now verified.")
                    else:
                        self._debug("SAS not marked as verified after MAC")

                except Exception as e:
                    self._debug(f"Error processing MAC: {e}")
                    import traceback
                    self._debug(traceback.format_exc())
            else:
                self._debug("No SAS for MAC verification")

        elif isinstance(event, KeyVerificationCancel):
            if self.current_verification == event.transaction_id or self.current_verification is None:
                print(f"\nVerification cancelled: {event.reason}")
                self.cancelled = True
            else:
                self._debug(f"Ignoring cancel for transaction {event.transaction_id}")

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
    # First, catch unknown events (including m.key.verification.request)
    client.add_to_device_callback(handler.handle_raw_event, UnknownToDeviceEvent)
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

        # Upload keys if needed
        if client.should_upload_keys:
            if debug:
                print("[DEBUG] Uploading keys...")
            await client.keys_upload()

        # Initial sync
        print("Syncing...")
        await client.sync(timeout=10000)

        if debug:
            print(f"[DEBUG] Active verifications: {list(client.key_verifications.keys())}")

        if request_device:
            # Query keys to get the device into our store
            print(f"Querying keys for verification target...")
            try:
                await client.keys_query()
            except Exception as e:
                if debug:
                    print(f"[DEBUG] Keys query skipped: {e}")

            # Try to find the device in our store
            user_id = config["user_id"]
            target_device = None

            if user_id in client.device_store:
                for dev_id, device in client.device_store[user_id].items():
                    if dev_id == request_device:
                        target_device = device
                        break

            if target_device:
                print(f"Found device {request_device}, starting verification...")
                # Use nio's proper verification start
                try:
                    msg = client.create_key_verification(target_device)
                    if msg:
                        await client.to_device(msg)
                        handler.current_verification = list(client.key_verifications.keys())[-1] if client.key_verifications else None
                        print(f"Verification request sent!")
                        if handler.current_verification:
                            print(f"Transaction ID: {handler.current_verification}")
                except Exception as e:
                    if debug:
                        print(f"[DEBUG] create_key_verification failed: {e}")
                    # Fall back to raw message
                    print("Falling back to direct request...")
                    import secrets
                    import time
                    txn_id = secrets.token_hex(16)
                    handler.current_verification = txn_id

                    request_content = {
                        "from_device": device_id,
                        "transaction_id": txn_id,
                        "methods": ["m.sas.v1"],
                        "timestamp": int(time.time() * 1000),
                    }

                    msg = ToDeviceMessage(
                        type="m.key.verification.request",
                        recipient=user_id,
                        recipient_device=request_device,
                        content=request_content,
                    )

                    resp = await client.to_device(msg)
                    if isinstance(resp, ToDeviceError):
                        print(f"Error sending request: {resp}", file=sys.stderr)
                        return False

                    print(f"Verification request sent!")
                    print(f"Transaction ID: {txn_id}")
            else:
                # Device not in store, send raw request
                print(f"Device {request_device} not in local store, sending direct request...")
                import secrets
                import time
                txn_id = secrets.token_hex(16)
                handler.current_verification = txn_id

                request_content = {
                    "from_device": device_id,
                    "transaction_id": txn_id,
                    "methods": ["m.sas.v1"],
                    "timestamp": int(time.time() * 1000),
                }

                msg = ToDeviceMessage(
                    type="m.key.verification.request",
                    recipient=user_id,
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
