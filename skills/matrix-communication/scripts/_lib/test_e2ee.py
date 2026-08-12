"""Tests for `_lib.e2ee` store-error diagnosis.

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

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from e2ee import explain_store_error, restore_login_checked


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
