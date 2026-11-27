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

import importlib.util
import json
import os
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
    def test_every_token_present_is_verified(self):
        """Regression (#70): admin_token short-circuited the check, so a dead
        access_token alongside a live admin_token reported OK."""
        self.responses = [OK, REJECTED]
        state, message = doctor.check_token(
            {**CONFIG, "admin_token": "syt_admin", "access_token": "syt_dead"}
        )
        self.assertIs(state, False)
        self.assertEqual(
            [token for token, _, _ in self.requests], ["syt_admin", "syt_dead"]
        )
        self.assertIn("access_token rejected", message)
        self.assertIn("admin_token valid", message)

    def test_both_tokens_valid(self):
        self.responses = [OK, OK]
        state, message = doctor.check_token(
            {**CONFIG, "admin_token": "syt_admin", "access_token": "syt_user"}
        )
        self.assertIs(state, True)
        self.assertIn("admin_token valid", message)
        self.assertIn("access_token valid", message)

    def test_single_token_still_verified(self):
        self.responses = [REJECTED]
        state, _ = doctor.check_token({**CONFIG, "access_token": "syt_dead"})
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
            {**CONFIG, "access_token": "syt_dead"}, store_ok=True
        )
        self.assertIs(state, False)
        self.assertIn("stale token", message)
        # The token may come from the environment or a token file, so the
        # remedy names every source, not only config.json.
        self.assertIn("MATRIX_ACCESS_TOKEN", message)
        self.assertIn("_token_file", message)
        # The advice must be the negated form, not the bare instruction.
        self.assertIn("do not mint a new token", message)
        self.assertNotIn("mint a new token for the skill", message)

    def test_rejected_token_without_a_working_store_still_says_mint(self):
        """The verdict never changes -- only the remedy. With no working store
        credential there is nothing to repair against, so the old advice stands."""
        self.responses = [REJECTED]
        state, message = doctor.check_token(
            {**CONFIG, "access_token": "syt_dead"}, store_ok=False
        )
        self.assertIs(state, False)
        self.assertIn("mint a new token", message)
        # The dead token may come from the environment or a token file.
        self.assertIn("MATRIX_ACCESS_TOKEN", message)

    def test_store_verdict_does_not_rescue_a_rejected_token(self):
        """A working store must not turn a dead config token green -- the two
        credentials serve different scripts."""
        self.responses = [REJECTED]
        state, _ = doctor.check_token(
            {**CONFIG, "access_token": "syt_dead"}, store_ok=True
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
        self.assertIn("matrix-e2ee-setup.py", message)

    def test_credential_of_another_device_fails(self):
        """Another client's token verifies fine - it just is not ours."""
        self._write_session()
        self.responses = [{**OK, "device_id": "ELEMENTBBBB"}]
        state, message = doctor.check_e2ee_setup(CONFIG)
        self.assertIs(state, False)
        self.assertIn("ELEMENTBBBB", message)
        self.assertIn("another client's token", message)

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


class CheckConfigTokenSourceTests(unittest.TestCase):
    """check_config resolves tokens the way the scripts do.

    Without that, a token kept in MATRIX_ACCESS_TOKEN or a token file makes the
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
        (self.config_dir / "access.token").write_text("syt_from_file\n")
        self.write_config({**CONFIG, "access_token_file": "access.token"})
        ok, _, config = doctor.check_config()
        self.assertIs(ok, True)
        self.assertEqual(config["access_token"], "syt_from_file")

    def test_environment_token_reaches_the_token_check(self):
        self.write_config(CONFIG)
        os.environ["MATRIX_ACCESS_TOKEN"] = "syt_from_env"
        ok, _, config = doctor.check_config()
        self.assertIs(ok, True)
        self.assertEqual(config["access_token"], "syt_from_env")

    def test_unreadable_token_file_fails_the_config_check(self):
        self.write_config({**CONFIG, "access_token_file": "absent.token"})
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
