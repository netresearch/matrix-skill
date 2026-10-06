# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH

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
        # delete_credentials takes the store lock, which creates its lock file
        # beside the store files; that file is not part of what is counted.
        return sorted(p.name for p in self.store.iterdir() if p.name != ".daemon.lock")

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

    def test_logout_refuses_while_another_process_holds_the_store(self):
        user, device = "@user:example.org", "DEVICEAAAA"
        db = self.store / f"{user}_{device}.db"
        db.write_text("x")
        (self.store / "credentials.json").write_text(
            json.dumps({"user_id": user, "device_id": device, "access_token": "t"})
        )
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

        with self.assertRaises(SystemExit):
            delete_credentials(lock_timeout=1)
        self.assertTrue(db.exists())
        self.assertTrue((self.store / "credentials.json").exists())


class PrivateStorageTests(unittest.TestCase):
    """Everything under the skill's data directory is readable by its owner only."""

    def setUp(self):
        self.home = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.home, True)
        old_env = os.environ.get("XDG_DATA_HOME")
        os.environ["XDG_DATA_HOME"] = str(self.home)
        self.addCleanup(
            lambda: (
                os.environ.__setitem__("XDG_DATA_HOME", old_env)
                if old_env is not None
                else os.environ.pop("XDG_DATA_HOME", None)
            )
        )
        old_umask = os.umask(0o022)
        self.addCleanup(os.umask, old_umask)

    def mode(self, path):
        return os.stat(path).st_mode & 0o777

    def test_data_store_and_rooms_directories_are_private(self):
        store = e2ee.get_store_path()
        rooms = e2ee.rooms_dir()
        self.assertEqual(self.mode(store.parent), 0o700)
        self.assertEqual(self.mode(store), 0o700)
        self.assertEqual(self.mode(rooms), 0o700)

    def test_existing_directories_are_tightened(self):
        root = self.home / "matrix-skill"
        (root / "store").mkdir(parents=True)
        (root / "rooms").mkdir()
        for path in (root, root / "store", root / "rooms"):
            # The looser mode an older version left behind, to be tightened.
            # nosemgrep: python.lang.security.audit.insecure-file-permissions.insecure-file-permissions
            os.chmod(path, 0o750)
        e2ee.get_store_path()
        e2ee.rooms_dir()
        for path in (root, root / "store", root / "rooms"):
            self.assertEqual(self.mode(path), 0o700, path)

    def test_credentials_file_is_created_owner_only(self):
        e2ee.save_credentials("@u:example.org", "DEV", "secret")
        path = e2ee.get_credentials_path()
        self.assertEqual(self.mode(path), 0o600)
        self.assertEqual(json.loads(path.read_text())["access_token"], "secret")

    def test_write_private_file_tightens_an_existing_file(self):
        target = self.home / "f.json"
        target.write_text("old")
        os.chmod(target, 0o640)
        e2ee.write_private_file(target, "new")
        self.assertEqual(self.mode(target), 0o600)
        self.assertEqual(target.read_text(), "new")

    def test_write_private_file_does_not_follow_a_symlink(self):
        elsewhere = self.home / "elsewhere.txt"
        elsewhere.write_text("untouched")
        link = self.home / "link.json"
        link.symlink_to(elsewhere)
        with self.assertRaises(OSError):
            e2ee.write_private_file(link, "secret")
        self.assertEqual(elsewhere.read_text(), "untouched")

    def test_verification_emoji_file_lives_in_the_private_directory(self):
        path = e2ee.verification_emoji_path()
        self.assertEqual(path.parent, e2ee.get_store_path().parent)
        e2ee.write_private_file(path, "emoji")
        self.assertEqual(self.mode(path), 0o600)


class VerificationPartnerTests(unittest.TestCase):
    """Verification is answered for the account's own devices unless another user is named."""

    OWN = "@agent:example.org"

    def test_own_account_allowed(self):
        self.assertTrue(e2ee.verification_partner_allowed(self.OWN, self.OWN))

    def test_other_user_refused_by_default(self):
        self.assertFalse(
            e2ee.verification_partner_allowed("@other:example.org", self.OWN)
        )

    def test_other_user_allowed_when_named(self):
        self.assertTrue(
            e2ee.verification_partner_allowed(
                "@other:example.org", self.OWN, ("@other:example.org",)
            )
        )

    def test_missing_sender_refused(self):
        self.assertFalse(e2ee.verification_partner_allowed(None, self.OWN))


if __name__ == "__main__":
    unittest.main(verbosity=2)
