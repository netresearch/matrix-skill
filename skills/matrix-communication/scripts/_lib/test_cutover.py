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
import shutil
import stat
import subprocess
import tempfile
import unittest.mock
from pathlib import Path

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
        patcher = unittest.mock.patch.dict(
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
        else:
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

    def test_a_backup_that_fails_stops_the_takeover_with_a_cutover_error(self):
        runner = FakeRunner()
        with unittest.mock.patch.object(
            cutover.shutil, "copytree", side_effect=PermissionError("denied")
        ):
            try:
                self.migrate(runner)
            except cutover.CutoverError as exc:
                self.assertIn("denied", str(exc))
            except OSError as exc:
                self.fail(f"{exc!r} escaped as a traceback")
            else:
                self.fail("the takeover ran without a backup")
        self.assertEqual(runner.calls, [])

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

    def failed_attempt(self):
        with self.assertRaises(cutover.CutoverError) as ctx:
            self.migrate(FakeRunner(rc=1, output="error: refused"))
        return str(ctx.exception)

    def test_a_retry_reuses_the_backup_of_an_unchanged_store(self):
        self.failed_attempt()
        message = self.failed_attempt()
        backups = cutover.existing_backups(self.store)
        self.assertEqual(len(backups), 1)
        self.assertIn(str(backups[0]), message)

    def test_a_changed_store_gets_a_new_backup_and_the_error_names_all(self):
        self.failed_attempt()
        (self.store / "@u:example.org_DEV.db").write_bytes(b"sqlite, changed")
        message = self.failed_attempt()
        backups = cutover.existing_backups(self.store)
        self.assertEqual(len(backups), 2)
        # Each path whole: one backup name can be the prefix of the next
        # (store.backup-<time> and store.backup-<time>.1).
        listed = message.split("are in: ", 1)[1].split(". To give up", 1)[0].split(", ")
        self.assertEqual(listed, [str(b) for b in backups])
        self.assertEqual(
            (backups[-1] / "@u:example.org_DEV.db").read_bytes(), b"sqlite, changed"
        )

    def test_the_lock_file_is_not_part_of_the_comparison(self):
        backup = cutover.backup_store(self.store)
        (self.store / ".daemon.lock").write_text("12345")
        self.assertEqual(cutover.tree_digest(backup), cutover.tree_digest(self.store))

    def test_a_held_store_lock_refuses_before_copying_or_migrating(self):
        runner = FakeRunner()
        with (
            open(self.store / ".daemon.lock", "r+b") as holder,
            self.assertRaises(cutover.CutoverError) as ctx,
        ):
            fcntl.flock(holder, fcntl.LOCK_EX)
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
        else:
            self.assertNotEqual(first, second)

    def test_nothing_happens_when_nothing_is_pending(self):
        cutover.marker_path(self.env).write_text("{}")
        runner = FakeRunner()
        self.assertIsNone(
            cutover.migrate_if_pending("/bin/cli", env=self.env, runner=runner)
        )
        self.assertEqual(runner.calls, [])


class TakeoverLockTests(CutoverTestCase):
    def setUp(self):
        super().setUp()
        self.make_nio_store()

    def test_a_takeover_finished_while_waiting_is_not_run_again(self):
        # pending() was true when the caller looked; by the time this process
        # holds the takeover lock another one has recorded the takeover.
        cutover.marker_path(self.env).write_text("{}")
        runner = FakeRunner()
        self.assertIsNone(self.migrate(runner))
        self.assertEqual(runner.calls, [])
        self.assertEqual(cutover.existing_backups(self.store), [])

    def lock_state(self):
        """(takeover lock held by someone, nio store lock free)."""
        path = self.root / "data" / "matrix-skill" / cutover.TAKEOVER_LOCK
        probe = os.open(path, os.O_RDWR)
        try:
            fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
            held = False
        except BlockingIOError:
            held = True
        finally:
            os.close(probe)
        store = os.open(self.store / ".daemon.lock", os.O_RDWR)
        try:
            fcntl.flock(store, fcntl.LOCK_EX | fcntl.LOCK_NB)
            free = True
        except BlockingIOError:
            free = False
        finally:
            os.close(store)
        return held, free

    def test_migrate_nio_runs_under_the_takeover_lock_with_the_store_lock_free(self):
        seen = []

        def runner(argv, **kwargs):
            seen.append(self.lock_state())
            return subprocess.CompletedProcess(argv, 0, stdout="")

        self.migrate(runner)
        self.assertEqual(seen, [(True, True)])


class ExplicitMigrateTests(CutoverTestCase):
    def setUp(self):
        super().setUp()
        self.calls = []

    def run_cli(self, rc=0, session=False):
        def run(binary, args, env):
            self.calls.append((binary, args))
            if session:
                path = cutover.cli_session_path(self.env)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("{}")
            return rc

        return run

    def explicit(self, args, **kwargs):
        return cutover.explicit_migrate(
            "/bin/cli",
            args,
            env=self.env,
            run=self.run_cli(**kwargs),
            log=self.logged.append,
        )

    def test_the_store_is_copied_before_the_cli_runs_with_the_arguments_unchanged(self):
        self.make_nio_store()
        args = ["migrate-nio", "--check-online"]
        self.assertEqual(self.explicit(args, session=True), 0)
        self.assertEqual(self.calls, [("/bin/cli", args)])
        backups = cutover.existing_backups(self.store)
        self.assertEqual(len(backups), 1)
        self.assertTrue((backups[0] / "credentials.json").is_file())
        marker = json.loads(cutover.marker_path(self.env).read_text())
        self.assertEqual(marker["backup"], str(backups[0]))
        self.assertFalse(cutover.pending(self.env))

    def test_no_session_before_and_none_after_records_nothing(self):
        self.make_nio_store()
        self.assertEqual(self.explicit(["migrate-nio"], rc=1), 1)
        self.assertFalse(cutover.marker_path(self.env).exists())
        self.assertEqual(len(cutover.existing_backups(self.store)), 1)

    def test_a_failed_run_that_wrote_the_session_is_recorded(self):
        # --check-online can exit 1 after the session was written: that
        # session is the device taken over, and a later logout must not lead
        # to a second takeover.
        self.make_nio_store()
        args = ["migrate-nio", "--check-online"]
        self.assertEqual(self.explicit(args, rc=1, session=True), 1)
        self.assertTrue(cutover.marker_path(self.env).exists())

    def test_a_session_that_was_there_before_records_nothing(self):
        self.make_nio_store()
        session = cutover.cli_session_path(self.env)
        session.parent.mkdir(parents=True)
        session.write_text("{}")
        self.assertEqual(self.explicit(["migrate-nio"], rc=1, session=True), 1)
        self.assertFalse(cutover.marker_path(self.env).exists())

    def test_a_backup_that_fails_is_a_cutover_error_and_nothing_runs(self):
        self.make_nio_store()
        with unittest.mock.patch.object(
            cutover.shutil, "copytree", side_effect=shutil.Error([("a", "b", "no")])
        ):
            try:
                self.explicit(["migrate-nio"])
            except cutover.CutoverError as exc:
                self.assertIn("cannot back up", str(exc))
            except OSError as exc:
                self.fail(f"{exc!r} escaped as a traceback")
            else:
                self.fail("migrate-nio ran without a backup")
        self.assertEqual(self.calls, [])

    def test_off_posix_the_cli_runs_unlocked_and_answers_itself(self):
        self.make_nio_store()
        with (
            unittest.mock.patch.object(cutover, "_posix", return_value=False),
            unittest.mock.patch.object(
                cutover, "takeover_lock", side_effect=AssertionError("locked")
            ),
        ):
            self.assertEqual(self.explicit(["migrate-nio"], rc=1), 1)
        self.assertEqual(self.calls, [("/bin/cli", ["migrate-nio"])])
        self.assertEqual(cutover.existing_backups(self.store), [])

    def test_a_store_given_with_store_is_the_one_copied(self):
        self.store = self.root / "elsewhere" / "nio"
        self.make_nio_store()
        for args in (
            ["migrate-nio", "--store", str(self.store)],
            ["migrate-nio", f"--store={self.store}"],
        ):
            with self.subTest(args=args):
                before = len(cutover.existing_backups(self.store))
                self.explicit(args)
                self.assertEqual(len(cutover.existing_backups(self.store)), before + 1)
                (self.store / "@u:example.org_DEV.db").write_bytes(
                    f"changed {before}".encode()
                )

    def test_without_credentials_there_is_nothing_to_copy(self):
        try:
            code = self.explicit(["migrate-nio"])
        except OSError as exc:
            self.fail(f"tried to copy a store that is not there: {exc}")
        else:
            self.assertEqual(code, 0)
        self.assertEqual(self.calls, [("/bin/cli", ["migrate-nio"])])
        self.assertFalse(
            self.store.parent.exists() and any(self.store.parent.glob("store.backup-*"))
        )


if __name__ == "__main__":
    unittest.main()
