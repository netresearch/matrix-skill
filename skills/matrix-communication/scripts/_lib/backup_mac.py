# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH

"""MAC check for sessions in an m.megolm_backup.v1.curve25519-aes-sha2 backup.

Stdlib only, so it can be tested without the crypto dependencies of
matrix-key-backup.py.
"""

import hashlib
import hmac

# The algorithm truncates HMAC-SHA-256 to its first 8 bytes.
BACKUP_MAC_LENGTH = 8


def backup_session_mac_ok(mac: bytes, mac_key: bytes, ciphertext: bytes) -> bool:
    """Whether ``mac`` authenticates ``ciphertext`` under ``mac_key``.

    The MAC must be exactly 8 bytes: a shorter one would compare against a
    shorter prefix and be correspondingly easier to guess. Two inputs are
    accepted - the ciphertext, as the specification says, and the empty
    string, which is what libolm's olm_pk_encrypt MACs and therefore what
    backups written by libolm-based clients (Element included) carry.
    """
    if len(mac) != BACKUP_MAC_LENGTH:
        return False
    for message in (ciphertext, b""):
        expected = hmac.new(mac_key, message, hashlib.sha256).digest()[
            :BACKUP_MAC_LENGTH
        ]
        if hmac.compare_digest(mac, expected):
            return True
    return False
