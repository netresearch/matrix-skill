# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH

"""Which devices an encrypted send hands the room key to.

Stdlib only: the nio client is passed in and used through the few attributes
named below, so this module can be tested without nio.

By default the room key goes to verified devices only. nio refuses to encrypt
for a room that contains a device which is neither verified, blacklisted nor
ignored, and `send_checked` reports every such device before nio does, with
what to do about it. `trust_unverified=True` is the explicit opt-in to share
with them anyway for this one send: nio records those devices as ignored while
it shares, and that record is removed again afterwards, so the opt-in does not
outlive the command and is never stored as verification.

Sends through one client are serialised: while a send with the opt-in is in
flight, nio's temporary "ignored" mark would let a concurrent strict send (the
daemon serves requests in parallel) pass the check and reuse the room key just
shared with an unverified device.
"""

import asyncio
import weakref

# One lock per client; the daemon's single client serialises all its sends.
_SEND_LOCKS: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()


class UntrustedDevicesError(Exception):
    """The room has devices that would receive the key but are not verified."""

    def __init__(self, devices):
        self.devices = list(devices)
        super().__init__(describe_untrusted(self.devices))


def untrusted_devices(client, user_ids) -> list:
    """Devices of ``user_ids`` that nio would refuse to share a room key with.

    That is every active device that is not this one and is neither verified,
    blacklisted nor ignored in the local store.
    """
    found = []
    own_device = getattr(client, "device_id", None)
    for user_id in user_ids:
        for device in client.device_store.active_user_devices(user_id):
            if device.id == own_device:
                continue
            if device.verified or device.blacklisted or device.ignored:
                continue
            found.append(device)
    return found


def describe_untrusted(devices) -> str:
    lines = ["The room has devices that are not verified, so the message was not sent:"]
    for device in devices:
        name = getattr(device, "display_name", "") or ""
        label = f" ({name})" if name else ""
        lines.append(f"  {device.user_id} {device.id}{label}")
    lines.append(
        "Verify them (matrix-e2ee-verify.py for your own devices), or pass "
        "--trust-unverified-devices to share this message's key with them anyway."
    )
    return "\n".join(lines)


def _devices(client, user_ids):
    for user_id in user_ids:
        yield from client.device_store.active_user_devices(user_id)


def _room_users(client, room_id, user_ids):
    room = getattr(client, "rooms", {}).get(room_id)
    return list(dict.fromkeys([*user_ids, *(getattr(room, "users", None) or [])]))


async def send_checked(
    client, room_id, user_ids, message_type, content, trust_unverified=False
):
    """``client.room_send`` for an encrypted room, sharing keys only as allowed.

    Raises UntrustedDevicesError instead of sending when unverified devices are
    present and ``trust_unverified`` is false - also for a device nio only
    learns about inside ``room_send`` (it may sync the members and query keys
    there), which nio reports as OlmUnverifiedDeviceError.
    """
    lock = _SEND_LOCKS.setdefault(client, asyncio.Lock())
    async with lock:
        return await _send_checked_locked(
            client, room_id, user_ids, message_type, content, trust_unverified
        )


async def _send_checked_locked(
    client, room_id, user_ids, message_type, content, trust_unverified
):
    pending = untrusted_devices(client, user_ids)
    if pending and not trust_unverified:
        raise UntrustedDevicesError(pending)
    ignored_before = {
        (d.user_id, d.id) for d in _devices(client, user_ids) if d.ignored
    }
    try:
        return await client.room_send(
            room_id=room_id,
            message_type=message_type,
            content=content,
            ignore_unverified_devices=bool(trust_unverified),
        )
    except Exception as exc:
        # Stdlib only: nio's exception is recognised by name.
        device = getattr(exc, "device", None)
        if type(exc).__name__ == "OlmUnverifiedDeviceError" and device is not None:
            raise UntrustedDevicesError([device]) from exc
        raise
    finally:
        if trust_unverified:
            # nio stores every device it shared with under
            # ignore_unverified_devices as "ignored" - including devices it
            # discovered during this send - and later shares with ignored
            # devices without asking. Reset every device that was not ignored
            # before, so the opt-in covers this send only. The reset is
            # unconditional because the in-memory trust state is not always
            # updated with the database row; nio returns False when there is
            # nothing to undo.
            for device in _devices(client, _room_users(client, room_id, user_ids)):
                if (device.user_id, device.id) not in ignored_before:
                    client.unignore_device(device)
