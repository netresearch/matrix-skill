# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH

"""Tests for `_lib.trust`: which devices an encrypted send shares the room key with.

Run directly (stdlib only, no nio):

    python3 skills/matrix-communication/scripts/_lib/test_trust.py
"""

import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from trust import UntrustedDevicesError, send_checked, untrusted_devices


class FakeDevice:
    def __init__(
        self, user_id, device_id, verified=False, blacklisted=False, ignored=False
    ):
        self.user_id = user_id
        self.id = device_id
        self.display_name = f"{device_id} name"
        self.verified = verified
        self.blacklisted = blacklisted
        self.ignored = ignored


class FakeDeviceStore:
    def __init__(self, devices):
        self.devices = devices

    def active_user_devices(self, user_id):
        return [d for d in self.devices if d.user_id == user_id]


class FakeClient:
    def __init__(self, devices, device_id="SELF"):
        self.device_id = device_id
        self.device_store = FakeDeviceStore(devices)
        self.sent = []
        self.unignored = []
        self.verified_calls = []

    async def room_send(self, **kwargs):
        self.sent.append(kwargs)
        return "response"

    def unignore_device(self, device):
        self.unignored.append(device.id)

    def verify_device(self, device):  # must never be called
        self.verified_calls.append(device.id)


ME = "@agent:example.org"
OTHER = "@other:example.org"


def run(coro):
    return asyncio.run(coro)


class UntrustedDevicesTests(unittest.TestCase):
    def test_lists_only_devices_nio_would_refuse(self):
        client = FakeClient(
            [
                FakeDevice(ME, "SELF"),
                FakeDevice(ME, "PHONE", verified=True),
                FakeDevice(OTHER, "BLOCKED", blacklisted=True),
                FakeDevice(OTHER, "KNOWN", ignored=True),
                FakeDevice(OTHER, "NEW"),
            ]
        )
        self.assertEqual(
            [d.id for d in untrusted_devices(client, [ME, OTHER])], ["KNOWN", "NEW"]
        )


class SendCheckedTests(unittest.TestCase):
    def test_refuses_and_sends_nothing_while_unverified_devices_are_present(self):
        client = FakeClient([FakeDevice(OTHER, "NEW")])
        sending = send_checked(client, "!r:example.org", [OTHER], "m.room.message", {})
        with self.assertRaises(UntrustedDevicesError) as caught:
            run(sending)
        self.assertEqual(client.sent, [])
        self.assertIn("NEW", str(caught.exception))
        self.assertIn("--trust-unverified-devices", str(caught.exception))

    def test_sends_strictly_when_every_device_is_verified(self):
        client = FakeClient([FakeDevice(OTHER, "PHONE", verified=True)])
        run(
            send_checked(
                client, "!r:example.org", [OTHER], "m.room.message", {"body": "x"}
            )
        )
        self.assertEqual(len(client.sent), 1)
        self.assertIs(client.sent[0]["ignore_unverified_devices"], False)
        self.assertEqual(client.unignored, [])

    def test_opt_in_shares_for_this_send_only_and_never_verifies(self):
        client = FakeClient([FakeDevice(OTHER, "NEW")])
        run(
            send_checked(
                client,
                "!r:example.org",
                [OTHER],
                "m.room.message",
                {},
                trust_unverified=True,
            )
        )
        self.assertIs(client.sent[0]["ignore_unverified_devices"], True)
        self.assertEqual(client.unignored, ["NEW"])
        self.assertEqual(client.verified_calls, [])

    def test_opt_in_is_undone_when_the_send_fails(self):
        class Failing(FakeClient):
            async def room_send(self, **kwargs):
                raise RuntimeError("network")

        client = Failing([FakeDevice(OTHER, "NEW")])
        sending = send_checked(
            client, "!r", [OTHER], "m.room.message", {}, trust_unverified=True
        )
        with self.assertRaises(RuntimeError):
            run(sending)
        self.assertEqual(client.unignored, ["NEW"])


class OlmUnverifiedDeviceError(Exception):
    """Stand-in for nio's exception, recognised by name."""

    def __init__(self, device):
        super().__init__(f"Device {device.id} is not verified")
        self.device = device


class NioLikeClient(FakeClient):
    """room_send behaves like nio 0.25: it may discover a device, then either
    refuses an unverified one or marks every unverified one ignored."""

    def __init__(self, devices, discovered=None):
        super().__init__(devices)
        self.discovered = discovered

    async def room_send(self, **kwargs):
        if self.discovered is not None:
            self.device_store.devices.append(self.discovered)
        for device in self.device_store.devices:
            if device.id == self.device_id or device.verified or device.ignored:
                continue
            if not kwargs["ignore_unverified_devices"]:
                raise OlmUnverifiedDeviceError(device)
            device.ignored = True
        self.sent.append(kwargs)
        return "response"

    def unignore_device(self, device):
        super().unignore_device(device)
        device.ignored = False


class DevicesFoundDuringSendTests(unittest.TestCase):
    def test_opt_in_resets_a_device_found_during_the_send(self):
        late = FakeDevice(OTHER, "LATE")
        client = NioLikeClient([FakeDevice(OTHER, "NEW")], discovered=late)
        run(
            send_checked(
                client, "!r", [OTHER], "m.room.message", {}, trust_unverified=True
            )
        )
        self.assertEqual(sorted(client.unignored), ["LATE", "NEW"])
        self.assertFalse(late.ignored)

    def test_strict_send_reports_a_device_found_during_the_send(self):
        late = FakeDevice(OTHER, "LATE")
        client = NioLikeClient(
            [FakeDevice(OTHER, "PHONE", verified=True)], discovered=late
        )
        sending = send_checked(client, "!r", [OTHER], "m.room.message", {})
        with self.assertRaises(UntrustedDevicesError) as caught:
            run(sending)
        self.assertIn("LATE", str(caught.exception))
        self.assertEqual(client.sent, [])

    def test_ignored_device_from_an_older_version_is_refused_without_opt_in(self):
        legacy = FakeDevice(OTHER, "LEGACY", ignored=True)
        client = NioLikeClient([legacy, FakeDevice(OTHER, "PHONE", verified=True)])
        sending = send_checked(client, "!r", [OTHER], "m.room.message", {})
        with self.assertRaises(UntrustedDevicesError) as caught:
            run(sending)
        self.assertIn("LEGACY", str(caught.exception))
        self.assertEqual(client.sent, [])

    def test_opt_in_also_resets_an_older_ignored_mark(self):
        legacy = FakeDevice(OTHER, "LEGACY", ignored=True)
        client = NioLikeClient([legacy])
        run(
            send_checked(
                client, "!r", [OTHER], "m.room.message", {}, trust_unverified=True
            )
        )
        self.assertFalse(legacy.ignored)


class SlowNioLikeClient(NioLikeClient):
    """Yields to the event loop after marking devices ignored, like a network round trip."""

    async def room_send(self, **kwargs):
        result = await super().room_send(**kwargs)
        for _ in range(5):
            await asyncio.sleep(0)
        return result


class ConcurrentSendTests(unittest.TestCase):
    def test_strict_send_waits_for_an_opted_in_send_on_the_same_client(self):
        client = SlowNioLikeClient([FakeDevice(OTHER, "NEW")])

        async def both():
            flagged = asyncio.create_task(
                send_checked(
                    client,
                    "!r",
                    [OTHER],
                    "m.room.message",
                    {"n": 1},
                    trust_unverified=True,
                )
            )
            await asyncio.sleep(0)
            strict = send_checked(client, "!r", [OTHER], "m.room.message", {"n": 2})
            return await asyncio.gather(flagged, strict, return_exceptions=True)

        flagged_result, strict_result = run(both())
        self.assertEqual(flagged_result, "response")
        self.assertIsInstance(strict_result, UntrustedDevicesError)
        self.assertEqual([sent["content"] for sent in client.sent], [{"n": 1}])


if __name__ == "__main__":
    unittest.main(verbosity=2)
