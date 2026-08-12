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
        self.store = Path(tempfile.mkdtemp())
        self.addCleanup(self._cleanup_store)
        real_store_path = doctor.get_store_path
        doctor.get_store_path = lambda: self.store
        self.addCleanup(setattr, doctor, "get_store_path", real_store_path)

    def _cleanup_store(self):
        for child in self.store.iterdir():
            child.unlink()
        self.store.rmdir()

    def _write_credentials(self, **fields):
        creds = {
            "user_id": "@user:example.org",
            "device_id": "DEVICEAAAA",
            "access_token": "syt_device",
        }
        creds.update(fields)
        (self.store / "credentials.json").write_text(json.dumps(creds))

    def test_revoked_credential_fails(self):
        """Regression (#71): the check read the file only, so a device that had
        been logged out server-side still reported 'E2EE device configured'."""
        self._write_credentials()
        self.responses = [REJECTED]
        state, message = doctor.check_e2ee_setup(CONFIG)
        self.assertIs(state, False)
        self.assertIn("DEVICEAAAA", message)
        self.assertIn("matrix-e2ee-setup.py", message)

    def test_credential_of_another_device_fails(self):
        """Another client's token verifies fine - it just is not ours."""
        self._write_credentials()
        self.responses = [{**OK, "device_id": "ELEMENTBBBB"}]
        state, message = doctor.check_e2ee_setup(CONFIG)
        self.assertIs(state, False)
        self.assertIn("ELEMENTBBBB", message)
        self.assertIn("another client's token", message)

    def test_live_credential_passes(self):
        self._write_credentials()
        self.responses = [OK]
        state, message = doctor.check_e2ee_setup(CONFIG)
        self.assertIs(state, True)
        self.assertIn("DEVICEAAAA", message)

    def test_missing_credentials_file(self):
        state, message = doctor.check_e2ee_setup(CONFIG)
        self.assertIs(state, False)
        self.assertIn("no credentials", message)
        self.assertEqual(self.requests, [])

    def test_credentials_without_token(self):
        self._write_credentials(access_token=None)
        state, message = doctor.check_e2ee_setup(CONFIG)
        self.assertIs(state, False)
        self.assertIn("no access_token", message)
        self.assertEqual(self.requests, [])

    def test_offline_is_unknown_not_ok(self):
        self._write_credentials()
        state, message = doctor.check_e2ee_setup(CONFIG, offline=True)
        self.assertIsNone(state)
        self.assertIn("--offline", message)
        self.assertEqual(self.requests, [])

    def test_unreachable_homeserver_is_unknown_not_ok(self):
        self._write_credentials()
        self.responses = [UNREACHABLE]
        state, _ = doctor.check_e2ee_setup(CONFIG)
        self.assertIsNone(state)


if __name__ == "__main__":
    unittest.main(verbosity=2)
