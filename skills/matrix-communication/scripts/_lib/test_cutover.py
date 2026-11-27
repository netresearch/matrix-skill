# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH

"""Tests for `_lib/cutover.py`: the one-time takeover of the matrix-nio device.

Run directly (stdlib only; migrate-nio is a fake runner, nothing is contacted):

    python3 skills/matrix-communication/scripts/_lib/test_cutover.py

Every test points HOME and XDG_DATA_HOME at a temporary directory, so the real
store of the machine running the tests is never read or copied.
"""

import os
import sys

_LIB = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != _LIB]
sys.path.insert(0, os.path.dirname(_LIB))

import fcntl
import json
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from _lib import cutover


class FakeRunner:
    def __init__(self, rc=0, output="Migrated device DEV of @u:example.org\n"):
        self.rc = rc
        self.output = output
        self.calls = []

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, self.rc, stdout=self.output)


class CutoverTestCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.env = {
            "HOME": str(self.root / "home"),
            "XDG_DATA_HOME": str(self.root / "data"),
        }
        # The process environment too: the lock refusal asks an old daemon's
        # socket for its pid, and that path comes from HOME / XDG_RUNTIME_DIR.
        patcher = mock.patch.dict(
            os.environ, {**self.env, "XDG_RUNTIME_DIR": str(self.root / "run")}
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.store = self.root / "data" / "matrix-skill" / "store"
        self.logged = []

    def make_nio_store(self):
        self.store.mkdir(parents=True)
        (self.store / "credentials.json").write_text(
            json.dumps(
                {
                    "user_id": "@u:example.org",
                    "device_id": "DEV",
                    "access_token": "syt_x",
                }
            )
        )
        (self.store / "@u:example.org_DEV.db").write_bytes(b"sqlite")
        (self.store / ".daemon.lock").write_text("")

    def migrate(self, runner):
        return cutover.migrate(
            "/bin/cli", env=self.env, runner=runner, log=self.logged.append
        )


class PendingTests(CutoverTestCase):
    def test_no_store_is_not_pending(self):
        self.assertFalse(cutover.pending(self.env))

    def test_a_nio_store_with_credentials_is_pending(self):
        self.make_nio_store()
        self.assertTrue(cutover.pending(self.env))

    def test_the_marker_ends_it_even_after_a_logout_removed_the_session(self):
        self.make_nio_store()
        cutover.marker_path(self.env).write_text("{}")
        self.assertFalse(cutover.pending(self.env))

    def test_an_existing_cli_session_is_left_alone(self):
        self.make_nio_store()
        session = cutover.cli_session_path(self.env)
        session.parent.mkdir(parents=True)
        session.write_text("{}")
        self.assertFalse(cutover.pending(self.env))

    def test_paths_follow_xdg_data_home_then_home(self):
        self.assertEqual(cutover.nio_store_path(self.env), self.store)
        self.assertEqual(
            cutover.cli_session_path({"HOME": "/home/u"}),
            Path("/home/u/.local/share/matrix-e2ee-cli/session.json"),
        )

    def test_userprofile_stands_in_for_a_missing_home_as_in_the_cli(self):
        try:
            path = cutover.cli_session_path({"USERPROFILE": "/profile"})
        except cutover.CutoverError as exc:
            self.fail(f"USERPROFILE was not used: {exc}")
        self.assertEqual(
            path, Path("/profile/.local/share/matrix-e2ee-cli/session.json")
        )


class MigrateTests(CutoverTestCase):
    def setUp(self):
        super().setUp()
        self.make_nio_store()

    def test_success_backs_up_runs_migrate_nio_and_records_it(self):
        runner = FakeRunner()
        backup = self.migrate(runner)
        self.assertEqual(len(runner.calls), 1)
        argv, kwargs = runner.calls[0]
        self.assertEqual(
            argv, ["/bin/cli", "migrate-nio", "--yes", "--store", str(self.store)]
        )
        # Its output must not reach this process's stdout: callers parse that.
        self.assertEqual(kwargs["stdout"], subprocess.PIPE)
        self.assertEqual(
            json.loads((backup / "credentials.json").read_text())["device_id"], "DEV"
        )
        self.assertTrue((backup / "@u:example.org_DEV.db").exists())
        self.assertFalse((backup / ".daemon.lock").exists())
        marker = json.loads(cutover.marker_path(self.env).read_text())
        self.assertEqual(marker["backup"], str(backup))
        self.assertFalse(cutover.pending(self.env))
        text = "\n".join(self.logged)
        self.assertIn("Migrated device DEV", text)
        self.assertIn(str(backup), text)
        self.assertNotIn("Event ID:", text)

    def test_the_backup_is_owner_only(self):
        backup = self.migrate(FakeRunner())
        self.assertEqual(stat.S_IMODE(backup.stat().st_mode), 0o700)
        for child in backup.iterdir():
            self.assertEqual(stat.S_IMODE(child.stat().st_mode), 0o600, child)

    def test_a_failed_migration_stops_and_leaves_no_marker(self):
        with self.assertRaises(cutover.CutoverError) as ctx:
            self.migrate(FakeRunner(rc=1, output="error: refused"))
        self.assertIn("exit 1", str(ctx.exception))
        self.assertFalse(cutover.marker_path(self.env).exists())
        self.assertTrue(cutover.pending(self.env))
        self.assertIn("error: refused", "\n".join(self.logged))

    def test_a_held_store_lock_refuses_before_copying_or_migrating(self):
        holder = os.open(self.store / ".daemon.lock", os.O_RDWR)
        self.addCleanup(os.close, holder)
        fcntl.flock(holder, fcntl.LOCK_EX)
        runner = FakeRunner()
        with self.assertRaises(cutover.CutoverError) as ctx:
            self.migrate(runner)
        self.assertIn("in use", str(ctx.exception))
        self.assertEqual(runner.calls, [])
        self.assertEqual(list(self.store.parent.glob("store.backup-*")), [])

    def test_two_backups_in_one_second_do_not_collide(self):
        first = cutover.backup_store(self.store)
        try:
            second = cutover.backup_store(self.store)
        except FileExistsError:
            self.fail("the second backup collided with the first")
        self.assertNotEqual(first, second)

    def test_nothing_happens_when_nothing_is_pending(self):
        cutover.marker_path(self.env).write_text("{}")
        runner = FakeRunner()
        self.assertIsNone(
            cutover.migrate_if_pending("/bin/cli", env=self.env, runner=runner)
        )
        self.assertEqual(runner.calls, [])


if __name__ == "__main__":
    unittest.main()
