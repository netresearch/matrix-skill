"""Tests for `_lib.e2ee`: store-error diagnosis and scoped credential deletion.

The skill directory contains a hyphen (`matrix-communication`) so it is not
importable as a package; run the file directly or use unittest discovery:

    python3 skills/matrix-communication/scripts/_lib/test_e2ee.py
    python3 -m unittest discover \\
        -s skills/matrix-communication/scripts/_lib -p 'test_e2ee.py'

Stdlib only. No nio, no libolm: the diagnosis identifies the failure by type
name and message precisely so this module can stay dependency-free, and these
tests hold it to that.

`e2ee` is imported directly rather than as `_lib.e2ee`: running this file puts
its own directory on sys.path, where `_lib/http.py` shadows the stdlib `http`
package and breaks `urllib` on the way in.
"""

import contextlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import e2ee
from e2ee import (
    delete_credentials,
    explain_store_error,
    restore_login_checked,
    store_files_for,
    store_lock,
)


class OlmAccountError(Exception):
    """Stand-in for the nio/libolm exception, matched by name."""


class SessionError(Exception):
    """Stand-in for the other nio error the diagnosis accepts."""


class ExplainStoreErrorTests(unittest.TestCase):
    def test_backend_mismatch_is_explained(self):
        hint = explain_store_error(OlmAccountError("BAD_ACCOUNT_KEY"))
        self.assertIsNotNone(hint)
        self.assertIn("backend mismatch", hint)
        self.assertIn("matrix-e2ee-setup.py --logout", hint)

    def test_hint_names_the_installed_version(self):
        """The version is what tells you which side of the pin you are on."""
        hint = explain_store_error(OlmAccountError("BAD_ACCOUNT_KEY"))
        self.assertRegex(hint, r"matrix-nio \(\d+\.\d+|matrix-nio \(unknown\)")

    def test_other_session_error_is_explained(self):
        self.assertIsNotNone(explain_store_error(SessionError("BAD_ACCOUNT_KEY")))

    def test_unrelated_message_is_not_claimed(self):
        self.assertIsNone(explain_store_error(OlmAccountError("OLM_INVALID_BASE64")))

    def test_unrelated_exception_type_is_not_claimed(self):
        """A ValueError mentioning the string is not this failure."""
        self.assertIsNone(explain_store_error(ValueError("BAD_ACCOUNT_KEY")))


class FakeClient:
    def __init__(self, raises=None):
        self.raises = raises
        self.calls = []

    def restore_login(self, user_id, device_id, access_token):
        self.calls.append((user_id, device_id, access_token))
        if self.raises:
            raise self.raises


class RestoreLoginCheckedTests(unittest.TestCase):
    """These cover the error translation. Locking has its own test below - if
    they took the real lock they would queue behind a running daemon, which is
    the correct behaviour and a useless thing to wait 30 seconds for here."""

    def setUp(self):
        real = e2ee._hold_store_lock
        e2ee._hold_store_lock = lambda: None
        self.addCleanup(setattr, e2ee, "_hold_store_lock", real)

    def test_the_store_lock_is_taken_before_opening(self):
        """The whole point of #96: no path opens the store unlocked."""
        taken = []
        e2ee._hold_store_lock = lambda: taken.append(True)
        restore_login_checked(FakeClient(), "@u:example.org", "D", "t")
        self.assertEqual(taken, [True])

    def test_success_passes_the_credentials_through(self):
        client = FakeClient()
        restore_login_checked(client, "@u:example.org", "DEVICE", "syt_token")
        self.assertEqual(client.calls, [("@u:example.org", "DEVICE", "syt_token")])

    def test_backend_mismatch_exits_with_the_diagnosis(self):
        client = FakeClient(raises=OlmAccountError("BAD_ACCOUNT_KEY"))
        with self.assertRaises(SystemExit) as caught:
            restore_login_checked(client, "@u:example.org", "DEVICE", "syt_token")
        self.assertIn("backend mismatch", str(caught.exception))

    def test_unrelated_error_is_reraised_untouched(self):
        """Only the one diagnosable failure is intercepted."""
        client = FakeClient(raises=ValueError("something else"))
        with self.assertRaises(ValueError):
            restore_login_checked(client, "@u:example.org", "DEVICE", "syt_token")


class StoreScopingTests(unittest.TestCase):
    """--logout must take one device's files and leave every other device alone.

    Regression for #81: the old code globbed `*.db` and `*_devices` across the
    shared store directory, so logging one device out destroyed the megolm
    history of all of them.
    """

    USER = "@user:example.org"
    MINE = "DEVICEAAAA"
    OTHER = "DEVICEBBBB"

    def setUp(self):
        self.store = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.store, True)
        real = e2ee.get_store_path
        e2ee.get_store_path = lambda: self.store
        self.addCleanup(setattr, e2ee, "get_store_path", real)

        for device in (self.MINE, self.OTHER):
            for suffix in (
                "db",
                "blacklisted_devices",
                "ignored_devices",
                "trusted_devices",
            ):
                (self.store / f"{self.USER}_{device}.{suffix}").write_text("x")

        # Not device-scoped, and the key import depends on it.
        (self.store / "backup_key.json").write_text("{}")
        (self.store / "credentials.json").write_text(
            json.dumps({"user_id": self.USER, "device_id": self.MINE})
        )

    def _names(self):
        return sorted(p.name for p in self.store.iterdir())

    def test_store_files_for_selects_one_device(self):
        names = sorted(p.name for p in store_files_for(self.USER, self.MINE))
        self.assertEqual(len(names), 4)
        self.assertTrue(all(self.MINE in n for n in names))

    def test_store_files_for_does_not_match_a_prefix_device_id(self):
        """A device id that is a prefix of another must not collect its files."""
        (self.store / f"{self.USER}_{self.MINE}EXTRA.db").write_text("x")
        names = [p.name for p in store_files_for(self.USER, self.MINE)]
        self.assertNotIn(f"{self.USER}_{self.MINE}EXTRA.db", names)

    def test_logout_removes_only_this_device(self):
        removed = delete_credentials()

        self.assertIn("credentials.json", removed)
        self.assertEqual(len([n for n in removed if self.MINE in n]), 4)

        left = self._names()
        self.assertEqual(len([n for n in left if self.OTHER in n]), 4)
        self.assertIn("backup_key.json", left)
        self.assertNotIn("credentials.json", left)

    def test_purge_all_removes_every_device(self):
        delete_credentials(purge_all=True)
        left = self._names()
        self.assertEqual([n for n in left if n.endswith("_devices")], [])
        self.assertEqual([n for n in left if n.endswith(".db")], [])
        self.assertIn("backup_key.json", left)

    def test_without_credentials_nothing_is_removed(self):
        """No credentials means no device to scope by - deleting nothing is right."""
        (self.store / "credentials.json").unlink()
        self.assertEqual(delete_credentials(), [])
        self.assertEqual(len(self._names()), 9)


class StoreLockTests(unittest.TestCase):
    """Exclusivity has to be enforced, not agreed.

    Regression for #96: the spec said every direct path takes the lock; only
    the daemon did, so nothing prevented a second process from opening the
    store beside it. That is the condition that produces an undecryptable
    message today and a corrupt store tomorrow.
    """

    def setUp(self):
        self.store = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.store, True)
        real = e2ee.get_store_path
        e2ee.get_store_path = lambda: self.store
        self.addCleanup(setattr, e2ee, "get_store_path", real)

    def test_the_lock_is_granted_when_free(self):
        with store_lock(timeout=1):
            self.assertTrue(e2ee.store_lock_path().exists())

    def test_it_is_released_on_the_way_out(self):
        with store_lock(timeout=1):
            pass
        with store_lock(timeout=1):
            pass

    def test_it_is_released_even_when_the_body_raises(self):
        """A command that dies mid-send must not leave the store locked for
        everyone else."""
        with contextlib.suppress(RuntimeError), store_lock(timeout=1):
            raise RuntimeError("boom")
        with store_lock(timeout=1):
            pass

    def test_a_held_lock_refuses_and_names_the_holder(self):
        script = (
            "import fcntl, sys, time\n"
            f"h = open({str(e2ee.store_lock_path())!r}, 'a+')\n"
            "fcntl.flock(h.fileno(), fcntl.LOCK_EX)\n"
            "h.seek(0); h.truncate(); h.write('4242'); h.flush()\n"
            "sys.stdout.write('held\\n'); sys.stdout.flush()\n"
            "time.sleep(20)\n"
        )
        holder = subprocess.Popen(
            [sys.executable, "-c", script], stdout=subprocess.PIPE, text=True
        )
        self.addCleanup(holder.kill)
        self.assertEqual(holder.stdout.readline().strip(), "held")

        with self.assertRaises(SystemExit) as caught, store_lock(timeout=1):
            pass
        self.assertIn("4242", str(caught.exception))
        self.assertIn("matrix-watchd", str(caught.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
