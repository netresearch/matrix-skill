# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH

"""Tests for `_lib.backup_mac`: a backed-up session needs its full 8-byte MAC.

Run directly (stdlib only):

    python3 skills/matrix-communication/scripts/_lib/test_backup_mac.py
"""

import hashlib
import hmac
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backup_mac import backup_session_mac_ok

KEY = b"k" * 32
CIPHERTEXT = b"ciphertext-bytes"


def mac_over(message: bytes) -> bytes:
    return hmac.new(KEY, message, hashlib.sha256).digest()[:8]


class BackupSessionMacTests(unittest.TestCase):
    def test_mac_over_the_ciphertext_accepted(self):
        self.assertTrue(backup_session_mac_ok(mac_over(CIPHERTEXT), KEY, CIPHERTEXT))

    def test_libolm_mac_over_the_empty_string_accepted(self):
        self.assertTrue(backup_session_mac_ok(mac_over(b""), KEY, CIPHERTEXT))

    def test_wrong_mac_rejected(self):
        self.assertFalse(backup_session_mac_ok(mac_over(b"other"), KEY, CIPHERTEXT))

    def test_truncated_mac_rejected_even_when_its_prefix_matches(self):
        full = mac_over(CIPHERTEXT)
        for length in (1, 4, 7):
            self.assertFalse(
                backup_session_mac_ok(full[:length], KEY, CIPHERTEXT), length
            )

    def test_longer_mac_rejected(self):
        full = hmac.new(KEY, CIPHERTEXT, hashlib.sha256).digest()
        self.assertFalse(backup_session_mac_ok(full, KEY, CIPHERTEXT))


if __name__ == "__main__":
    unittest.main(verbosity=2)
