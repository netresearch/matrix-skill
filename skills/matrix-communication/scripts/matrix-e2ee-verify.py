#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["matrix-nio[e2e]"]
# ///
"""Interactive device verification for Matrix E2EE.

This script initiates verification and displays emojis for the user to confirm.
The user must confirm the emojis match in Element to complete verification.

Usage:
    matrix-e2ee-verify.py                    # Auto-find device and verify
    matrix-e2ee-verify.py --request DEVICE   # Verify with specific device
    matrix-e2ee-verify.py --list             # List your devices

The script will:
1. Find another device (or use specified device)
2. Initiate verification
3. Display 7 emojis that must match Element
4. Wait for user to confirm in Element
5. Complete verification and fetch room keys
"""

import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib import load_config, get_store_path, load_credentials

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
        UnknownToDeviceEvent,
        ToDeviceError,
        DevicesResponse,
        MegolmEvent,
        RoomMessagesResponse,
    )
    try:
        from nio import KeyVerificationRequest
    except ImportError:
        KeyVerificationRequest = None
except ImportError as e:
    if "olm" in str(e).lower():
        print("Error: libolm library not found.", file=sys.stderr)
        sys.exit(1)
    raise


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
        """Handle raw to-device events."""
        if isinstance(event, UnknownToDeviceEvent) and hasattr(event, 'source'):
            source = event.source

            if source.get('type') == 'm.key.verification.request':
                content = source.get('content', {})
                txn_id = content.get('transaction_id')
                from_device = content.get('from_device')
                methods = content.get('methods', [])
                sender = source.get('sender')

                print(f"\nVerification request received from {from_device}")

                if 'm.sas.v1' in methods:
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

                    await self.client.to_device(msg)
                    print("Ready sent, waiting for emoji exchange...")

            elif source.get('type', '').startswith('m.key.verification.'):
                self._debug(f"Verification event: {source.get('type')}")

    async def handle_event(self, event):
        """Handle verification events."""
        event_type = type(event).__name__
        self._debug(f"Received {event_type}")

        if KeyVerificationRequest and isinstance(event, KeyVerificationRequest):
            print(f"\nVerification request from {event.sender}")
            self.current_verification = event.transaction_id
            try:
                await self.client.accept_key_verification(event.transaction_id)
                print("Accepted, waiting for emoji exchange...")
            except Exception as e:
                self._debug(f"Error accepting: {e}")

        elif isinstance(event, KeyVerificationStart):
            if self.sas_accepted:
                return
            print(f"Verification started")
            self.current_verification = event.transaction_id
            try:
                await self.client.accept_key_verification(event.transaction_id)
                self.sas_accepted = True
            except Exception as e:
                self._debug(f"Error accepting: {e}")

        elif isinstance(event, KeyVerificationAccept):
            print("Other device accepted")

        elif isinstance(event, KeyVerificationKey):
            if self.key_sent:
                return

            sas = self.client.key_verifications.get(event.transaction_id)
            if not sas:
                self._debug(f"No SAS for {event.transaction_id}")
                return

            try:
                self.emojis = sas.get_emoji()

                # Build emoji display
                emoji_lines = []
                emoji_lines.append("")
                emoji_lines.append("╔══════════════════════════════════════════════════════════╗")
                emoji_lines.append("║           🔐 VERIFICATION EMOJIS - COMPARE NOW! 🔐        ║")
                emoji_lines.append("╠══════════════════════════════════════════════════════════╣")
                emoji_lines.append("║                                                          ║")

                for emoji, name in self.emojis:
                    line = f"       {emoji}    {name}"
                    padding = 58 - len(line)
                    emoji_lines.append(f"║{line}{' ' * padding}║")

                emoji_lines.append("║                                                          ║")
                emoji_lines.append("╠══════════════════════════════════════════════════════════╣")
                emoji_lines.append("║  👆 These emojis must EXACTLY match what Element shows!  ║")
                emoji_lines.append("║                                                          ║")
                emoji_lines.append("║  ➡️  Go to Element now and confirm the emojis match      ║")
                emoji_lines.append("║  ➡️  Click 'They match' in Element to complete           ║")
                emoji_lines.append("╚══════════════════════════════════════════════════════════╝")
                emoji_lines.append("")

                # Write to file for agent polling (before stdout which may be buffered)
                emoji_file = "/tmp/matrix_verification_emojis.txt"
                with open(emoji_file, "w") as f:
                    f.write("\n".join(emoji_lines))

                # Also print to stdout
                for line in emoji_lines:
                    print(line)

                # Share our key
                key_msg = sas.share_key()
                if key_msg:
                    await self.client.to_device(key_msg)
                self.key_sent = True

                # Accept our side (user confirms in Element)
                sas.accept_sas()
                mac_msg = sas.get_mac()
                if mac_msg:
                    await self.client.to_device(mac_msg)

                print("Waiting for you to confirm in Element...")

            except Exception as e:
                self._debug(f"Error in key exchange: {e}")

        elif isinstance(event, KeyVerificationMac):
            if self.verified:
                return

            sas = self.client.key_verifications.get(event.transaction_id)
            if sas:
                try:
                    sas.receive_mac_event(event)

                    if sas.verified:
                        self.verified = True
                        print("\n✅ VERIFICATION SUCCESSFUL!")

                        done_content = {"transaction_id": event.transaction_id}
                        done_msg = ToDeviceMessage(
                            type="m.key.verification.done",
                            recipient=event.sender,
                            recipient_device=sas.other_device_id if hasattr(sas, 'other_device_id') else sas.other_olm_device.device_id,
                            content=done_content,
                        )
                        await self.client.to_device(done_msg)

                except Exception as e:
                    self._debug(f"Error processing MAC: {e}")

        elif isinstance(event, KeyVerificationCancel):
            print(f"\n❌ Verification cancelled: {event.reason}")
            self.cancelled = True


async def run_verification(config: dict, request_device: str = None, timeout: int = 120, debug: bool = False):
    """Run verification process."""
    store_path = get_store_path()
    creds = load_credentials()

    if not creds or creds.get("user_id") != config["user_id"]:
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

    print(f"This device: {device_id}")

    client_config = AsyncClientConfig(store_sync_tokens=True, encryption_enabled=True)
    client = AsyncClient(
        homeserver=config["homeserver"],
        user=config["user_id"],
        device_id=device_id,
        store_path=str(store_path),
        config=client_config,
    )

    handler = VerificationHandler(client, debug=debug)

    client.add_to_device_callback(handler.handle_raw_event, UnknownToDeviceEvent)
    client.add_to_device_callback(handler.handle_event, KeyVerificationEvent)
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

        if client.should_upload_keys:
            if debug:
                print("[DEBUG] Uploading keys...")
            await client.keys_upload()

        print("Syncing...")
        await client.sync(timeout=10000)

        # Find target device if not specified
        if not request_device:
            print("Finding another device to verify with...")
            resp = await client.devices()
            if isinstance(resp, DevicesResponse):
                other_devices = [d for d in resp.devices if d.id != device_id]
                if other_devices:
                    # Filter and prioritize devices
                    def device_priority(d):
                        name = (d.display_name or "").lower()
                        # Skip backup devices (can't respond interactively)
                        if "backup" in name:
                            return (4, name)  # Lowest priority
                        # Prefer Element clients (desktop/mobile - interactive)
                        if "element" in name:
                            return (0, name)  # Highest priority
                        # Then riot/web clients
                        if "riot" in name or "chrome" in name or "firefox" in name:
                            return (1, name)
                        # Named devices
                        if d.display_name:
                            return (2, name)
                        # Unnamed devices last
                        return (3, name)

                    sorted_devices = sorted(other_devices, key=device_priority)
                    target = sorted_devices[0]
                    request_device = target.id
                    print(f"Target device: {target.display_name or target.id} ({target.id})")
                else:
                    print("No other devices found!", file=sys.stderr)
                    print("Open Element on another device first.", file=sys.stderr)
                    return False

        # Initiate verification
        print(f"\nInitiating verification with {request_device}...")

        # Query keys first
        try:
            await client.keys_query()
        except Exception as e:
            if debug:
                print(f"[DEBUG] Keys query: {e}")

        # Try to find device in store
        user_id = config["user_id"]
        target_device = None
        if user_id in client.device_store:
            for dev_id, device in client.device_store[user_id].items():
                if dev_id == request_device:
                    target_device = device
                    break

        # Send verification request
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
            print(f"Error: {resp}", file=sys.stderr)
            return False

        print("Verification request sent!")
        print("\n📱 Check Element for the verification popup")
        print(f"   Timeout: {timeout} seconds\n")

        # Wait for verification
        start_time = asyncio.get_event_loop().time()
        while not handler.verified and not handler.cancelled:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout:
                print("\n⏰ Timeout waiting for verification.")
                return False

            await client.sync(timeout=5000)

        # Post-verification: fetch room keys
        if handler.verified:
            print("\n📦 Fetching room keys from verified devices...")

            rooms_checked = 0
            for room_id, room in list(client.rooms.items())[:10]:
                if room.encrypted:
                    rooms_checked += 1
                    try:
                        result = await client.room_messages(room_id, start="", limit=50)
                        if isinstance(result, RoomMessagesResponse):
                            for event in result.chunk:
                                if isinstance(event, MegolmEvent):
                                    try:
                                        await client.request_room_key(event)
                                    except Exception:
                                        pass
                    except Exception:
                        pass

            print(f"   Checked {rooms_checked} encrypted rooms")
            print("   Waiting for keys (30s)...")

            for i in range(6):
                await client.sync(timeout=5000)
                if (i + 1) % 2 == 0:
                    print(f"   ... {(i+1)*5}s")

            print("\n🎉 Device verified and keys synced!")
            print("   Use matrix-fetch-keys.py ROOM for additional keys")

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

    client_config = AsyncClientConfig(store_sync_tokens=True, encryption_enabled=True)
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

    parser = argparse.ArgumentParser(
        description="Verify this device with another device using emoji verification",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                    # Auto-find device and start verification
  %(prog)s --request DEVICE   # Verify with specific device
  %(prog)s --list             # List all your devices

The script will display 7 emojis that must match what Element shows.
Confirm the match in Element to complete verification.
        """
    )
    parser.add_argument("--request", metavar="DEVICE", help="Target specific device ID")
    parser.add_argument("--list", action="store_true", help="List all your devices")
    parser.add_argument("--timeout", type=int, default=120, help="Timeout in seconds (default: 120)")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")

    args = parser.parse_args()
    config = load_config(require_user_id=True)

    if args.list:
        devices = asyncio.run(list_devices(config))
        if not devices:
            print("No devices found or error")
            sys.exit(1)

        print("Your devices:")
        for d in devices:
            marker = " ← this device" if d["is_current"] else ""
            print(f"  {d['device_id']}: {d['display_name']}{marker}")
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
