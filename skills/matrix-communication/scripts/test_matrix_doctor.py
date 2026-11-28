# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH

"""Tests for `matrix-doctor.py` credential checks.

The script name contains a hyphen so it is not importable as a module; it is
loaded by path. Run the file directly or use unittest discovery:

    python3 skills/matrix-communication/scripts/test_matrix_doctor.py
    python3 -m unittest discover \\
        -s skills/matrix-communication/scripts -p 'test_matrix_doctor.py'

Stdlib only. No homeserver is contacted - `http.matrix_request` is replaced by a
queue of canned responses, so a test that forgets to stub fails loudly rather
than reaching the network.
"""

import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "matrix_doctor", os.path.join(_HERE, "matrix-doctor.py")
)
doctor = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(doctor)

CONFIG = {
    "homeserver": "https://matrix.example.org",
    "user_id": "@user:example.org",
}
OK = {"user_id": "@user:example.org", "device_id": "DEVICEAAAA"}
REJECTED = {"error": "Invalid access token passed.", "errcode": "M_UNKNOWN_TOKEN"}
UNREACHABLE = {"error": "[Errno -2] Name or service not known"}


class CredentialTestCase(unittest.TestCase):
    """Replaces the transport with a response queue, one entry per request."""

    def setUp(self):
        self.requests = []
        self.responses = []
        self._real_request = doctor.http.matrix_request
        doctor.http.matrix_request = self._fake_request
        self.addCleanup(setattr, doctor.http, "matrix_request", self._real_request)

    def _fake_request(self, config, method, endpoint, data=None):
        self.requests.append((config.get("access_token"), method, endpoint))
        if not self.responses:
            raise AssertionError(f"unstubbed request: {method} {endpoint}")
        return self.responses.pop(0)


class CheckTokenTests(CredentialTestCase):
    def test_the_config_access_token_is_never_sent(self):
        """No script uses the config's access_token any more, so the doctor
        does not send it to the homeserver either."""
        self.responses = [OK]
        state, message = doctor.check_token(
            {**CONFIG, "admin_token": "syt_admin", "access_token": "syt_old"}
        )
        self.assertIs(state, True)
        self.assertEqual([token for token, _, _ in self.requests], ["syt_admin"])
        self.assertNotIn("access_token", message)

    def test_an_access_token_alone_is_nothing_to_verify(self):
        state, _ = doctor.check_token({**CONFIG, "access_token": "syt_old"})
        self.assertIsNone(state)
        self.assertEqual(self.requests, [])

    def test_admin_token_verified(self):
        self.responses = [REJECTED]
        state, _ = doctor.check_token({**CONFIG, "admin_token": "syt_dead"})
        self.assertIs(state, False)

    def test_unreachable_homeserver_is_unknown_not_ok(self):
        self.responses = [UNREACHABLE]
        state, message = doctor.check_token({**CONFIG, "admin_token": "syt_admin"})
        self.assertIsNone(state)
        self.assertIn("Could not verify", message)

    def test_rejected_token_with_a_working_store_advises_repair_not_a_new_token(self):
        """The W36 failure: 'both Matrix tokens are rejected' was reported as a
        blocker and the work parked, while the store held a live credential.
        A rejected config token beside a working store is a stale config."""
        self.responses = [REJECTED]
        state, message = doctor.check_token(
            {**CONFIG, "admin_token": "syt_dead"}, store_ok=True
        )
        self.assertIs(state, False)
        self.assertIn("stale token", message)
        # The token may come from the environment or a token file, so the
        # remedy names every source, not only config.json.
        self.assertIn("MATRIX_ADMIN_TOKEN", message)
        self.assertIn("admin_token_file", message)
        self.assertNotIn("MATRIX_ACCESS_TOKEN", message)
        # The advice must be the negated form, not the bare instruction.
        self.assertIn("do not mint a new token", message)
        self.assertNotIn("mint a new token for the skill", message)

    def test_rejected_token_without_a_working_store_still_says_mint(self):
        """The verdict never changes -- only the remedy. With no working store
        credential there is nothing to repair against, so the old advice stands."""
        self.responses = [REJECTED]
        state, message = doctor.check_token(
            {**CONFIG, "admin_token": "syt_dead"}, store_ok=False
        )
        self.assertIs(state, False)
        self.assertIn("mint a new token", message)
        # The dead token may come from the environment or a token file.
        self.assertIn("MATRIX_ADMIN_TOKEN", message)
        self.assertNotIn("MATRIX_ACCESS_TOKEN", message)

    def test_store_verdict_does_not_rescue_a_rejected_token(self):
        """A working store must not turn a dead config token green -- the two
        credentials serve different scripts."""
        self.responses = [REJECTED]
        state, _ = doctor.check_token(
            {**CONFIG, "admin_token": "syt_dead"}, store_ok=True
        )
        self.assertIs(state, False)

    def test_token_for_another_account_fails(self):
        self.responses = [{"user_id": "@someone-else:example.org"}]
        state, message = doctor.check_token({**CONFIG, "admin_token": "syt_admin"})
        self.assertIs(state, False)
        self.assertIn("@someone-else:example.org", message)

    def test_no_token_is_unknown(self):
        state, _ = doctor.check_token(dict(CONFIG))
        self.assertIsNone(state)
        self.assertEqual(self.requests, [])

    def test_offline_skips_the_call(self):
        state, message = doctor.check_token(
            {**CONFIG, "admin_token": "syt_admin"}, offline=True
        )
        self.assertIsNone(state)
        self.assertIn("--offline", message)
        self.assertEqual(self.requests, [])


class CheckE2eeSetupTests(CredentialTestCase):
    def setUp(self):
        super().setUp()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.session = Path(tmp.name) / "session.json"
        self.nio_pending = False
        for name, value in (
            ("get_session_path", lambda: self.session),
            ("nio_pending", lambda: self.nio_pending),
        ):
            real = getattr(doctor, name)
            setattr(doctor, name, value)
            self.addCleanup(setattr, doctor, name, real)

    def _write_session(self, **fields):
        session = {
            "homeserver": "https://matrix.example.org",
            "user_id": "@user:example.org",
            "device_id": "DEVICEAAAA",
            "access_token": "syt_device",
        }
        session.update(fields)
        self.session.write_text(json.dumps(session))

    def test_revoked_credential_fails(self):
        """Regression (#71): the check read the file only, so a device that had
        been logged out server-side still reported 'E2EE device configured'."""
        self._write_session()
        self.responses = [REJECTED]
        state, message = doctor.check_e2ee_setup(CONFIG)
        self.assertIs(state, False)
        self.assertIn("DEVICEAAAA", message)
        self.assertIn("matrix-e2ee-setup.py --force", message)

    def test_credential_of_another_device_fails(self):
        """Another client's token verifies fine - it just is not ours."""
        self._write_session()
        self.responses = [{**OK, "device_id": "ELEMENTBBBB"}]
        state, message = doctor.check_e2ee_setup(CONFIG)
        self.assertIs(state, False)
        self.assertIn("ELEMENTBBBB", message)
        self.assertIn("another client's token", message)
        self.assertIn("matrix-e2ee-setup.py --force", message)

    def test_setup_command_names_force_only_when_a_session_exists(self):
        self.assertEqual(doctor.setup_command(), "matrix-e2ee-setup.py")
        self._write_session()
        self.assertEqual(doctor.setup_command(), "matrix-e2ee-setup.py --force")

    def test_live_credential_passes(self):
        self._write_session()
        self.responses = [OK]
        state, message = doctor.check_e2ee_setup(CONFIG)
        self.assertIs(state, True)
        self.assertIn("DEVICEAAAA", message)
        self.assertEqual(self.requests, [("syt_device", "GET", "/account/whoami")])

    def test_no_home_at_all_fails_instead_of_raising(self):
        def no_home():
            raise doctor.cutover.CutoverError("neither XDG_DATA_HOME nor HOME is set")

        doctor.get_session_path = no_home
        try:
            state, message = doctor.check_e2ee_setup(CONFIG)
        except doctor.cutover.CutoverError:
            self.fail("check_e2ee_setup raised instead of failing the check")
        else:
            self.assertIs(state, False)
            self.assertIn("HOME", message)

    def test_missing_session_file(self):
        state, message = doctor.check_e2ee_setup(CONFIG)
        self.assertIs(state, False)
        self.assertIn("no matrix-e2ee-cli session", message)
        self.assertEqual(self.requests, [])

    def test_a_nio_device_waiting_for_its_takeover_is_unknown_not_failed(self):
        self.nio_pending = True
        state, message = doctor.check_e2ee_setup(CONFIG)
        self.assertIsNone(state)
        self.assertIn("migrate-nio", message)
        self.assertEqual(self.requests, [])

    def test_session_without_token(self):
        self._write_session(access_token=None)
        state, message = doctor.check_e2ee_setup(CONFIG)
        self.assertIs(state, False)
        self.assertIn("no access_token", message)
        self.assertIn("matrix-e2ee-setup.py --force", message)
        self.assertEqual(self.requests, [])

    def test_offline_is_unknown_not_ok(self):
        self._write_session()
        state, message = doctor.check_e2ee_setup(CONFIG, offline=True)
        self.assertIsNone(state)
        self.assertIn("--offline", message)
        self.assertEqual(self.requests, [])

    def test_unreachable_homeserver_is_unknown_not_ok(self):
        self._write_session()
        self.responses = [UNREACHABLE]
        state, _ = doctor.check_e2ee_setup(CONFIG)
        self.assertIsNone(state)

    def test_a_session_without_homeserver_fails_and_sends_nothing(self):
        # Its token belongs to its own homeserver only: never to config.json's.
        for homeserver in (None, ""):
            with self.subTest(homeserver=homeserver):
                self._write_session(homeserver=homeserver)
                self.requests.clear()
                state, message = doctor.check_e2ee_setup(CONFIG)
                self.assertIs(state, False)
                self.assertIn("no homeserver", message)
                self.assertEqual(self.requests, [])

    def test_the_token_is_checked_where_matrix_e2ee_cli_uses_it(self):
        self._write_session(homeserver="https://device.example.net")
        seen = []
        real = self._fake_request

        def record(config, method, endpoint, data=None):
            seen.append(config["homeserver"])
            return real(config, method, endpoint, data)

        doctor.http.matrix_request = record
        self.responses = [OK]
        state, _ = doctor.check_e2ee_setup(CONFIG)
        self.assertIs(state, True)
        self.assertEqual(seen, ["https://device.example.net"])


class CheckConfigTokenSourceTests(unittest.TestCase):
    """check_config resolves tokens the way the scripts do.

    Without that, a token kept in MATRIX_ADMIN_TOKEN or a token file makes the
    doctor report "No token in config" while every script authenticates fine.
    """

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.config_dir = Path(tmp.name) / "matrix"
        self.config_dir.mkdir()
        env = {k: v for k, v in os.environ.items() if not k.startswith("MATRIX_")}
        env["XDG_CONFIG_HOME"] = tmp.name
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write_config(self, data):
        (self.config_dir / "config.json").write_text(json.dumps(data))

    def test_token_file_reaches_the_token_check(self):
        (self.config_dir / "admin.token").write_text("syt_from_file\n")
        self.write_config({**CONFIG, "admin_token_file": "admin.token"})
        ok, _, config = doctor.check_config()
        self.assertIs(ok, True)
        self.assertEqual(config["admin_token"], "syt_from_file")

    def test_environment_token_reaches_the_token_check(self):
        self.write_config(CONFIG)
        os.environ["MATRIX_ADMIN_TOKEN"] = "syt_from_env"
        ok, _, config = doctor.check_config()
        self.assertIs(ok, True)
        self.assertEqual(config["admin_token"], "syt_from_env")

    def test_access_token_sources_are_not_resolved(self):
        self.write_config({**CONFIG, "access_token_file": "absent.token"})
        os.environ["MATRIX_ACCESS_TOKEN"] = "syt_from_env"
        ok, message, config = doctor.check_config()
        self.assertIs(ok, True, message)
        self.assertNotIn("access_token", config)

    def test_unreadable_token_file_fails_the_config_check(self):
        self.write_config({**CONFIG, "admin_token_file": "absent.token"})
        ok, message, _ = doctor.check_config()
        self.assertIs(ok, False)
        self.assertIn("absent.token", message)


class CheckE2eeCliTests(unittest.TestCase):
    """The e2ee_cli row: the pinned binary, or MATRIX_E2EE_CLI's."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        env = {
            "HOME": str(self.dir / "home"),
            "XDG_DATA_HOME": str(self.dir / "data"),
            "PATH": os.environ.get("PATH", ""),
        }
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def fake_cli(self, rc=0):
        path = self.dir / "fake-cli"
        path.write_text(f"#!/bin/sh\necho 'matrix-e2ee-cli 9.9.9'\nexit {rc}\n")
        path.chmod(0o755)
        os.environ["MATRIX_E2EE_CLI"] = str(path)
        return path

    def test_the_doctor_declares_no_dependency(self):
        source = Path(_HERE, "matrix-doctor.py").read_text()
        self.assertIn("# dependencies = []\n", source)

    def test_a_working_binary_passes_with_its_version(self):
        path = self.fake_cli()
        ok, message = doctor.check_e2ee_cli()
        self.assertIs(ok, True)
        self.assertIn("matrix-e2ee-cli 9.9.9", message)
        self.assertIn(str(path), message)

    def test_a_binary_that_fails_fails(self):
        self.fake_cli(rc=3)
        ok, message = doctor.check_e2ee_cli()
        self.assertIs(ok, False)
        self.assertIn("exited 3", message)

    def test_a_missing_binary_names_the_pinned_version_and_the_fix(self):
        version = doctor.cli.load_release()["version"]
        with mock.patch.object(doctor.cli, "ensure_binary") as ensure:
            ok, message = doctor.check_e2ee_cli()
        self.assertIs(ok, False)
        self.assertIn(version, message)
        self.assertIn("--install", message)
        ensure.assert_not_called()

    def test_install_downloads(self):
        path = self.fake_cli()
        del os.environ["MATRIX_E2EE_CLI"]
        with mock.patch.object(
            doctor.cli, "ensure_binary", return_value=path
        ) as ensure:
            ok, _ = doctor.check_e2ee_cli(install=True)
        self.assertIs(ok, True)
        ensure.assert_called_once()

    def test_install_offline_downloads_nothing(self):
        with mock.patch.object(doctor.cli, "ensure_binary") as ensure:
            ok, _ = doctor.check_e2ee_cli(install=True, offline=True)
        self.assertIs(ok, False)
        ensure.assert_not_called()

    def test_a_filesystem_error_is_a_failed_row_not_a_crash(self):
        with mock.patch.object(
            doctor.cli, "find_binary", side_effect=PermissionError("denied")
        ):
            try:
                ok, message = doctor.check_e2ee_cli()
            except OSError:
                self.fail("check_e2ee_cli raised instead of failing the row")
            else:
                self.assertIs(ok, False)
                self.assertIn("unusable", message)
                self.assertIn("denied", message)


class QuickFixTests(unittest.TestCase):
    """The quick fix main() prints for a rejected config token.

    Reproduces the review case: the E2EE device works, the config token is
    stale and the config check fails, so the quick fix is printed. A session
    file exists, so any setup advice would carry --force.
    """

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        session = Path(tmp.name) / "session.json"
        session.write_text("{}")
        self.e2ee = (True, "E2EE device confirmed by the homeserver: DEVICEAAAA")
        patches = {
            "get_session_path": lambda: session,
            "check_e2ee_cli": lambda install=False, offline=False: (True, "cli"),
            "check_config": lambda: (False, "Token source unusable", dict(CONFIG)),
            "check_e2ee_setup": lambda config, offline=False: self.e2ee,
            "check_token": lambda config, offline=False, store_ok=None: (
                False,
                "access_token rejected by the homeserver (M_UNKNOWN_TOKEN)",
            ),
        }
        for name, value in patches.items():
            patcher = mock.patch.object(doctor, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def quick_fix(self):
        out = io.StringIO()
        with (
            mock.patch.object(sys, "argv", ["matrix-doctor.py"]),
            contextlib.redirect_stdout(out),
            self.assertRaises(SystemExit),
        ):
            doctor.main()
        text = out.getvalue()
        self.assertIn("Quick fix:", text)
        return text.split("Quick fix:", 1)[1]

    def test_a_working_device_with_a_stale_config_token_gets_no_force(self):
        text = self.quick_fix()
        self.assertNotIn("--force", text)
        self.assertIn("stale config token", text)
        # A rejected admin_token is repaired where it is set too.
        self.assertIn("MATRIX_ADMIN_TOKEN", text)
        self.assertIn("an admin_token needs a server-admin token", text)
        # No script reads access_token any more: no advice to set one.
        self.assertNotIn("access_token", text)
        self.assertNotIn("MATRIX_ACCESS_TOKEN", text)

    def test_an_unverified_device_gets_no_force_either(self):
        self.e2ee = (
            None,
            "E2EE device DEVICEAAAA configured - not verified (--offline)",
        )
        text = self.quick_fix()
        self.assertNotIn("--force", text)
        self.assertIn("could not be checked", text)

    def test_a_rejected_device_gets_the_force_remedy(self):
        self.e2ee = (False, "E2EE credential (DEVICEAAAA) rejected by the homeserver")
        text = self.quick_fix()
        self.assertIn("Token rejected: mint a new one for the skill", text)
        self.assertIn("matrix-e2ee-setup.py --force", text)


class StaleTokenRowTests(CredentialTestCase):
    """What a user with a valid config and a stale config token sees.

    The config check passes, so there is no Quick fix footer: the advice is
    in the token row itself, and the real check_token produces it from a
    homeserver rejection.
    """

    def setUp(self):
        super().setUp()
        config = {**CONFIG, "admin_token": "syt_dead"}
        patches = {
            "check_e2ee_cli": lambda install=False, offline=False: (True, "cli"),
            "check_config": lambda: (True, "Config OK", dict(config)),
            "check_e2ee_setup": lambda config, offline=False: (
                True,
                "E2EE device confirmed by the homeserver: DEVICEAAAA",
            ),
        }
        for name, value in patches.items():
            patcher = mock.patch.object(doctor, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_the_token_row_advises_repair_without_force(self):
        self.responses = [REJECTED]
        out = io.StringIO()
        with (
            mock.patch.object(sys, "argv", ["matrix-doctor.py"]),
            contextlib.redirect_stdout(out),
            self.assertRaises(SystemExit) as ctx,
        ):
            doctor.main()
        self.assertEqual(ctx.exception.code, 0)
        text = out.getvalue()
        self.assertNotIn("Quick fix:", text)
        row = text.split("[FAIL] token", 1)[1].split("\n\n", 1)[0]
        self.assertIn("stale token", row)
        self.assertIn("do not mint a new token", row)
        self.assertNotIn("--force", text)
        self.assertEqual(self.requests, [("syt_dead", "GET", "/account/whoami")])


class LeftoverAccessTokenTests(unittest.TestCase):
    """An access_token left in the config gets a warning that it is unused.

    The device it belongs to is named only when the doctor can tell without a
    request: the token is the one in matrix-e2ee-cli's session.json.
    """

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.session = Path(tmp.name) / "session.json"
        self.session.write_text(
            json.dumps({"device_id": "SKILLDEV", "access_token": "syt_device"})
        )
        patcher = mock.patch.object(
            doctor, "get_session_path", return_value=self.session
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        env = {k: v for k, v in os.environ.items() if not k.startswith("MATRIX_")}
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.requests = []
        real = doctor.http.matrix_request
        doctor.http.matrix_request = lambda *a, **k: self.requests.append(a)
        self.addCleanup(setattr, doctor.http, "matrix_request", real)

    def test_the_skills_own_token_is_named_as_its_device(self):
        message = doctor.check_leftover_token({**CONFIG, "access_token": "syt_device"})
        self.assertIn("no longer used", message)
        self.assertIn("SKILLDEV", message)
        self.assertEqual(self.requests, [])

    def test_another_token_gets_the_warning_without_a_device(self):
        message = doctor.check_leftover_token({**CONFIG, "access_token": "syt_other"})
        self.assertIn("no longer used", message)
        self.assertNotIn("SKILLDEV", message)
        self.assertNotIn("syt_other", message)
        self.assertEqual(self.requests, [])

    def test_a_token_file_or_variable_is_a_leftover_too(self):
        self.assertIn(
            "access_token_file",
            doctor.check_leftover_token({**CONFIG, "access_token_file": "t"}),
        )
        os.environ["MATRIX_ACCESS_TOKEN"] = "syt_env"
        self.assertIn("MATRIX_ACCESS_TOKEN", doctor.check_leftover_token(CONFIG))

    def test_no_leftover_no_warning(self):
        self.assertIsNone(doctor.check_leftover_token(dict(CONFIG)))

    def test_the_warning_is_a_row_that_fails_nothing(self):
        patches = {
            "check_e2ee_cli": lambda install=False, offline=False: (True, "cli"),
            "check_config": lambda: (
                True,
                "Config OK",
                {**CONFIG, "access_token": "syt_device"},
            ),
            "check_e2ee_setup": lambda config, offline=False: (True, "device ok"),
            "check_token": lambda config, offline=False, store_ok=None: (True, "ok"),
        }
        for name, value in patches.items():
            patcher = mock.patch.object(doctor, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        out = io.StringIO()
        with (
            mock.patch.object(sys, "argv", ["matrix-doctor.py"]),
            contextlib.redirect_stdout(out),
            self.assertRaises(SystemExit) as ctx,
        ):
            doctor.main()
        self.assertEqual(ctx.exception.code, 0)
        text = out.getvalue()
        self.assertIn("[WARN] access_token", text)
        self.assertIn("SKILLDEV", text)
        self.assertIn("All checks passed", text)


class RequiredSessionTests(unittest.TestCase):
    """Every script needs the CLI session: a session that is definitely
    missing or rejected fails the doctor; one it could not check does not."""

    def run_main(self, e2ee, *argv):
        patches = {
            "check_e2ee_cli": lambda install=False, offline=False: (True, "cli"),
            "check_config": lambda: (True, "Config OK", dict(CONFIG)),
            "check_e2ee_setup": lambda config, offline=False: e2ee,
            "check_token": lambda config, offline=False, store_ok=None: (None, "none"),
            "check_leftover_token": lambda config: None,
        }
        with contextlib.ExitStack() as stack:
            for name, value in patches.items():
                stack.enter_context(mock.patch.object(doctor, name, value))
            out = io.StringIO()
            stack.enter_context(
                mock.patch.object(sys, "argv", ["matrix-doctor.py", *argv])
            )
            stack.enter_context(contextlib.redirect_stdout(out))
            with self.assertRaises(SystemExit) as ctx:
                doctor.main()
        return ctx.exception.code, out.getvalue()

    def test_a_missing_or_rejected_session_fails(self):
        for e2ee in (
            (False, "E2EE not set up (no matrix-e2ee-cli session)"),
            (False, "E2EE credential (DEV) rejected by the homeserver"),
        ):
            with self.subTest(e2ee=e2ee[1]):
                code, text = self.run_main(e2ee)
                self.assertEqual(code, 1)
                self.assertIn("[FAIL] e2ee_setup (required)", text)
                self.assertNotIn("Core functionality OK", text)
                code, text = self.run_main(e2ee, "--json")
                self.assertEqual(code, 1)
                self.assertIs(json.loads(text)["e2ee_setup"]["critical"], True)

    def test_an_unchecked_session_does_not_fail(self):
        for e2ee in (
            (None, "E2EE device DEV configured - not verified (--offline)"),
            (None, "E2EE device of an older version (matrix-nio) not taken over yet"),
        ):
            with self.subTest(e2ee=e2ee[1]):
                code, _ = self.run_main(e2ee)
                self.assertEqual(code, 0)
                code, _ = self.run_main(e2ee, "--json")
                self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
