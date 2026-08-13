#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["matrix-nio[e2e]<0.26", "cryptography", "aiohttp"]
# ///
"""
Fetch and decrypt keys from Matrix key backup using recovery key or passphrase.

Usage:
    matrix-key-backup.py --import-keys                     # Reuse the stored backup key
    matrix-key-backup.py --recovery-key "EsTj qRGp ..."   # Use recovery key
    matrix-key-backup.py --passphrase "your passphrase"   # Use passphrase
    matrix-key-backup.py --status                          # Check backup status

The first form works once a recovery key or passphrase has been used at least
once: that run stores the decrypted backup key in the E2EE store directory, and
later runs reuse it as long as it matches the backup version on the server.
"""

import argparse
import asyncio
import base64
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aiohttp
from _lib import (
    get_store_path,
    load_config,
    load_credentials,
    restore_login_checked,
)
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives import hmac as crypto_hmac
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from nio import AsyncClient, AsyncClientConfig
from nio.crypto import InboundGroupSession

sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)


# Base58 alphabet for recovery key
BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def decode_base58(s: str) -> bytes:
    """Decode a base58 string to bytes."""
    s = s.replace(" ", "")
    result = 0
    for char in s:
        result = result * 58 + BASE58_ALPHABET.index(char)
    byte_length = (result.bit_length() + 7) // 8
    return result.to_bytes(byte_length, "big")


def decode_recovery_key(recovery_key: str) -> bytes:
    """Decode a Matrix recovery key to get the SSSS key."""
    decoded = decode_base58(recovery_key)

    # Check prefix 0x8B 0x01
    if decoded[:2] != b"\x8b\x01":
        raise ValueError(f"Invalid recovery key prefix: {decoded[:2].hex()}")

    # Remove prefix (2 bytes) and parity byte (1 byte at end)
    key = decoded[2:-1]

    if len(key) != 32:
        raise ValueError(f"Invalid key length: {len(key)}, expected 32")

    return key


def derive_key_from_passphrase(passphrase: str, key_info: dict) -> bytes:
    """Derive SSSS key from passphrase using PBKDF2."""
    passphrase_info = key_info.get("passphrase", {})
    algorithm = passphrase_info.get("algorithm", "m.pbkdf2")

    if algorithm != "m.pbkdf2":
        raise ValueError(f"Unsupported passphrase algorithm: {algorithm}")

    salt_b64 = passphrase_info.get("salt")
    iterations = passphrase_info.get("iterations", 500000)
    bits = passphrase_info.get("bits", 256)

    if not salt_b64:
        raise ValueError("No salt in key info")

    salt = base64.b64decode(salt_b64)

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA512(),
        length=bits // 8,
        salt=salt,
        iterations=iterations,
    )

    return kdf.derive(passphrase.encode("utf-8"))


def decode_unpadded_base64(data: str) -> bytes:
    """Decode base64 with missing padding."""
    padding = 4 - (len(data) % 4)
    if padding != 4:
        data += "=" * padding
    return base64.b64decode(data)


def derive_ssss_keys(secret: bytes) -> tuple[bytes, bytes]:
    """Derive AES and HMAC keys for SSSS decryption."""
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=64,
        salt=b"\x00" * 32,
        info=b"",
    )
    derived = hkdf.derive(secret)
    return derived[:32], derived[32:]


def decrypt_ssss(encrypted_data: dict, ssss_key: bytes) -> bytes:
    """Decrypt SSSS-encrypted data."""
    iv = base64.b64decode(encrypted_data["iv"])
    ciphertext = base64.b64decode(encrypted_data["ciphertext"])
    mac = base64.b64decode(encrypted_data["mac"])

    aes_key, hmac_key = derive_ssss_keys(ssss_key)

    # Verify MAC
    h = crypto_hmac.HMAC(hmac_key, hashes.SHA256())
    h.update(ciphertext)
    expected_mac = h.finalize()

    if mac != expected_mac:
        raise ValueError("MAC verification failed - wrong recovery key/passphrase?")

    # Decrypt
    cipher = Cipher(algorithms.AES(aes_key), modes.CTR(iv))
    decryptor = cipher.decryptor()
    return decryptor.update(ciphertext) + decryptor.finalize()


def derive_backup_keys(backup_key: bytes) -> tuple[bytes, bytes]:
    """Derive AES and HMAC keys for backup decryption."""
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=64,
        salt=b"\x00" * 32,
        info=b"",
    )
    derived = hkdf.derive(backup_key)
    return derived[:32], derived[32:]


def decrypt_backup_session(encrypted: dict, backup_key: bytes) -> dict:
    """Decrypt a backed up megolm session."""
    # Algorithm: m.megolm_backup.v1.curve25519-aes-sha2
    # The session data is encrypted with:
    # 1. ECDH with backup public key to get shared secret
    # 2. HKDF to derive AES and MAC keys
    # 3. AES-CBC + HMAC-SHA256

    ephemeral_b64 = encrypted.get("session_data", {}).get("ephemeral")
    ciphertext_b64 = encrypted.get("session_data", {}).get("ciphertext")
    mac_b64 = encrypted.get("session_data", {}).get("mac")

    if not all([ephemeral_b64, ciphertext_b64, mac_b64]):
        raise ValueError("Missing session data fields")

    ephemeral = decode_unpadded_base64(ephemeral_b64)
    ciphertext = decode_unpadded_base64(ciphertext_b64)
    mac = decode_unpadded_base64(mac_b64)

    # ECDH: shared_secret = backup_private_key * ephemeral_public
    private_key = X25519PrivateKey.from_private_bytes(backup_key)
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PublicKey

    ephemeral_public = X25519PublicKey.from_public_bytes(ephemeral)
    shared_secret = private_key.exchange(ephemeral_public)

    # Derive keys using HKDF. The spec splits the 80 bytes 32/32/16: AES key,
    # MAC key, and the AES-CBC IV. The IV is derived here, it is NOT carried in
    # the ciphertext - reading it off the front of the ciphertext decrypts the
    # first block to garbage and usually dies on the padding check.
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=80,
        salt=b"",
        info=b"",
    )
    derived = hkdf.derive(shared_secret)

    aes_key = derived[:32]
    mac_key = derived[32:64]
    iv = derived[64:80]

    # Verify the MAC. The spec computes it over the ciphertext and truncates to
    # 8 bytes, so compare only as many bytes as the backup carries.
    h = crypto_hmac.HMAC(mac_key, hashes.SHA256())
    h.update(ciphertext)
    spec_mac = h.finalize()

    if mac != spec_mac[: len(mac)]:
        # libolm's olm_pk_encrypt MACs the empty string rather than the
        # ciphertext. Backups written by any libolm-based client - which is
        # most of them, Element included - carry that MAC, so a strict check
        # rejects every session in the backup rather than a tampered one.
        # Accept exactly that one alternative and nothing else.
        h = crypto_hmac.HMAC(mac_key, hashes.SHA256())
        h.update(b"")
        if mac != h.finalize()[: len(mac)]:
            raise ValueError("Session MAC verification failed")

    # Decrypt using AES-CBC (not CTR!)
    cipher = Cipher(algorithms.AES(aes_key), modes.CBC(iv))
    decryptor = cipher.decryptor()
    padded_plaintext = decryptor.update(ciphertext) + decryptor.finalize()

    # Remove PKCS7 padding
    pad_len = padded_plaintext[-1]
    plaintext = padded_plaintext[:-pad_len]

    return json.loads(plaintext)


def load_stored_backup_key(store_path, backup_info: dict) -> bytes | None:
    """Return the backup key a previous run stored, if it fits this backup.

    A successful SSSS decryption writes the key to ``backup_key.json`` "for
    future use", and until now nothing read it back: every run demanded the
    recovery key again. Two things have to line up before the stored key may be
    used - the backup version it was saved for, and the public key the server
    publishes for the current backup. A rotated backup leaves a stale file
    behind, and a key that decrypts nothing is worse than asking for the
    recovery key.
    """
    key_file = store_path / "backup_key.json"
    if not key_file.exists():
        return None

    try:
        stored = json.loads(key_file.read_text())
        key = base64.b64decode(stored["backup_key"])
    except (OSError, ValueError, KeyError) as e:
        print(f"Ignoring {key_file}: {e}")
        return None

    if str(stored.get("version")) != str(backup_info.get("version")):
        print(
            f"Ignoring stored backup key: saved for version {stored.get('version')}, "
            f"server is on {backup_info.get('version')}"
        )
        return None

    try:
        public = X25519PrivateKey.from_private_bytes(key).public_key()
        derived = base64.b64encode(public.public_bytes_raw()).decode()
    except ValueError as e:
        print(f"Ignoring stored backup key: {e}")
        return None

    expected = backup_info.get("auth_data", {}).get("public_key", "")
    if derived.rstrip("=") != expected.rstrip("="):
        print("Ignoring stored backup key: public key does not match this backup")
        return None

    return key


async def main():
    parser = argparse.ArgumentParser(description="Matrix key backup")
    parser.add_argument("--recovery-key", help="Recovery key (base58 format)")
    parser.add_argument("--passphrase", help="Recovery passphrase")
    parser.add_argument("--status", action="store_true", help="Show backup status")
    parser.add_argument(
        "--import-keys", action="store_true", help="Import keys after decryption"
    )
    args = parser.parse_args()

    config = load_config(require_user_id=True)
    creds = load_credentials()

    if not creds:
        print("No credentials. Run matrix-e2ee-setup.py first.", file=sys.stderr)
        return 1

    headers = {"Authorization": f"Bearer {creds['access_token']}"}
    store_path = get_store_path()

    async with aiohttp.ClientSession() as session:
        # Get backup version info
        url = f"{config['homeserver']}/_matrix/client/v3/room_keys/version"
        async with session.get(url, headers=headers) as resp:
            if resp.status == 404:
                print("No key backup found on server.")
                return 1
            elif resp.status != 200:
                print(f"Error getting backup version: {resp.status}")
                return 1
            backup_info = await resp.json()

        print("=== Key Backup Info ===")
        print(f"Version: {backup_info.get('version')}")
        print(f"Algorithm: {backup_info.get('algorithm')}")
        auth_data = backup_info.get("auth_data", {})
        print(f"Public key: {auth_data.get('public_key')}")

        if args.status:
            # Get key count
            version = backup_info.get("version")
            url = f"{config['homeserver']}/_matrix/client/v3/room_keys/keys?version={version}"
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    keys_data = await resp.json()
                    rooms = keys_data.get("rooms", {})
                    session_count = sum(
                        len(sessions.get("sessions", {})) for sessions in rooms.values()
                    )
                    print(f"Rooms with backups: {len(rooms)}")
                    print(f"Total sessions: {session_count}")
            return 0

        # A previous run stores the decrypted backup key next to the E2EE store.
        # Use it when it fits this backup version, so a re-import does not need
        # the recovery key again. An explicit --recovery-key/--passphrase wins:
        # that is how you recover after the backup version was rotated.
        stored_key = None
        if not args.recovery_key and not args.passphrase:
            stored_key = load_stored_backup_key(store_path, backup_info)
            if stored_key is None:
                print("\nTo restore keys, provide --recovery-key or --passphrase")
                print("\nYour recovery key looks like: EsTj qRGp YB4C ...")
                return 1
            print("\n=== Backup Key ===")
            print(f"Using stored key: {store_path / 'backup_key.json'}")

        if stored_key is not None:
            backup_key = stored_key
        else:
            # Get default SSSS key info
            url = f"{config['homeserver']}/_matrix/client/v3/user/{config['user_id']}/account_data/m.secret_storage.default_key"
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    print(f"No SSSS key info found: {resp.status}")
                    return 1
                default_key_data = await resp.json()
                default_key_id = default_key_data.get("key")

            # Get key info for passphrase derivation
            url = f"{config['homeserver']}/_matrix/client/v3/user/{config['user_id']}/account_data/m.secret_storage.key.{default_key_id}"
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    print(f"Could not get key info: {resp.status}")
                    return 1
                key_info = await resp.json()

            # Derive SSSS key
            print("\n=== Deriving SSSS Key ===")
            if args.recovery_key:
                ssss_key = decode_recovery_key(args.recovery_key)
                print("Using recovery key")
            else:
                ssss_key = derive_key_from_passphrase(args.passphrase, key_info)
                print("Derived key from passphrase")

            # Get encrypted backup key from SSSS
            url = f"{config['homeserver']}/_matrix/client/v3/user/{config['user_id']}/account_data/m.megolm_backup.v1"
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    print(f"No backup key in SSSS: {resp.status}")
                    return 1
                backup_ssss = await resp.json()

            encrypted = backup_ssss.get("encrypted", {}).get(default_key_id)
            if not encrypted:
                print(f"No encryption data for key {default_key_id}")
                return 1

            # Decrypt backup key
            print("\n=== Decrypting Backup Key ===")
            try:
                backup_key = decrypt_ssss(encrypted, ssss_key)
                print(f"✅ Backup key decrypted ({len(backup_key)} bytes)")

                # Verify public key matches
                private = X25519PrivateKey.from_private_bytes(backup_key)
                public = private.public_key().public_bytes_raw()
                public_b64 = base64.b64encode(public).decode()
                expected_public = auth_data.get("public_key")

                print(f"   Derived public:  {public_b64}")
                print(f"   Expected public: {expected_public}")

                if public_b64 != expected_public:
                    print("❌ Public key mismatch!")
                    return 1
                print("✅ Public key verified!")

            except ValueError as e:
                print(f"❌ Decryption failed: {e}")
                return 1

            # Save backup key for future use
            backup_key_file = store_path / "backup_key.json"
            backup_key_payload = json.dumps(
                {
                    "backup_key": base64.b64encode(backup_key).decode(),
                    "version": backup_info.get("version"),
                    "algorithm": backup_info.get("algorithm"),
                },
                indent=2,
            )
            await asyncio.to_thread(backup_key_file.write_text, backup_key_payload)
            await asyncio.to_thread(os.chmod, backup_key_file, 0o600)
            print(f"\n✅ Backup key saved to: {backup_key_file}")

        if not args.import_keys:
            print("\nUse --import-keys to fetch and import room keys from backup")
            return 0

        # Fetch and import keys
        print("\n=== Fetching Keys from Backup ===")
        version = backup_info.get("version")
        url = (
            f"{config['homeserver']}/_matrix/client/v3/room_keys/keys?version={version}"
        )
        async with session.get(url, headers=headers) as resp:
            if resp.status != 200:
                print(f"Failed to fetch keys: {resp.status}")
                return 1
            keys_data = await resp.json()

        rooms = keys_data.get("rooms", {})
        print(f"Found {len(rooms)} rooms with backups")

        # Connect to nio client for importing
        client_config = AsyncClientConfig(
            store_sync_tokens=True, encryption_enabled=True
        )
        client = AsyncClient(
            homeserver=config["homeserver"],
            user=config["user_id"],
            device_id=creds["device_id"],
            store_path=str(store_path),
            config=client_config,
        )

        try:
            restore_login_checked(
                client, config["user_id"], creds["device_id"], creds["access_token"]
            )
            if client.store:
                client.load_store()

            await client.sync(timeout=5000)

            imported = 0
            already_present = 0
            failed = 0

            # room_id is part of the megolm session identity, so it has to come
            # from the key it was filed under - iterate items(), not values().
            for room_id, room_data in rooms.items():
                sessions = room_data.get("sessions", {})
                for session_id, session_data in sessions.items():
                    try:
                        decrypted = decrypt_backup_session(session_data, backup_key)

                        signing_key = decrypted.get("sender_claimed_keys", {}).get(
                            "ed25519"
                        )
                        sender_key = decrypted.get("sender_key")
                        session_key = decrypted.get("session_key")
                        if not (signing_key and sender_key and session_key):
                            raise ValueError("session is missing key material")

                        session = InboundGroupSession.import_session(
                            session_key,
                            signing_key,
                            sender_key,
                            room_id,
                            decrypted.get("forwarding_curve25519_key_chain") or [],
                        )

                        # Go through the in-memory store first, the way nio does
                        # when it imports a key itself. add() returns False for a
                        # session already held, and the database write is an
                        # on_conflict_ignore insert - so counting every decrypted
                        # session as imported would report writes that never
                        # happened. Sessions loaded from the store at startup are
                        # in that in-memory set, which is what makes this honest
                        # on a re-import.
                        if client.olm.inbound_group_store.add(session):
                            client.olm.store.save_inbound_group_session(session)
                            imported += 1
                        else:
                            already_present += 1

                        if imported and imported % 500 == 0:
                            print(f"  Imported {imported} sessions...")

                    except Exception as e:  # noqa: BLE001  # intentional fail-soft: error surfaced to caller, not re-raised
                        failed += 1
                        if failed <= 5:
                            print(f"  Failed on session {session_id[:20]}: {e}")

            print("\n=== Import Complete ===")
            print(f"Imported: {imported}")
            if already_present:
                print(f"Already in the store: {already_present}")
            print(f"Failed: {failed}")
            if failed and not imported and not already_present:
                return 1

        finally:
            await client.close()

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
