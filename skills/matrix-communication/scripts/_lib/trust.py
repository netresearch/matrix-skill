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
"""


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


async def send_checked(
    client, room_id, user_ids, message_type, content, trust_unverified=False
):
    """``client.room_send`` for an encrypted room, sharing keys only as allowed.

    Raises UntrustedDevicesError instead of sending when unverified devices are
    present and ``trust_unverified`` is false.
    """
    pending = untrusted_devices(client, user_ids)
    if pending and not trust_unverified:
        raise UntrustedDevicesError(pending)
    try:
        return await client.room_send(
            room_id=room_id,
            message_type=message_type,
            content=content,
            ignore_unverified_devices=bool(pending),
        )
    finally:
        # nio stores the devices it shared with under ignore_unverified_devices
        # as "ignored", and later shares with ignored devices without asking.
        # Undo that, so the opt-in covers this send only.
        # The in-memory trust state is not always updated with the database
        # row, so the reset is unconditional; nio returns False when there is
        # nothing to undo.
        for device in pending:
            client.unignore_device(device)
