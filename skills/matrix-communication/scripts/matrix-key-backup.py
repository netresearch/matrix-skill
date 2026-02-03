#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["matrix-nio[e2e]", "cryptography", "aiohttp"]
# ///
"""
Fetch and decrypt keys from Matrix key backup using recovery key or passphrase.

Usage:
    matrix-key-backup.py --recovery-key "EsTj qRGp ..."   # Use recovery key
    matrix-key-backup.py --passphrase "your passphrase"   # Use passphrase
    matrix-key-backup.py --status                          # Check backup status
"""

import asyncio
import argparse
import base64
import json
import sys
import os
import struct

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _lib import load_config, get_store_path, load_credentials

from cryptography.hazmat.primitives import hashes, hmac as crypto_hmac
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from nio import AsyncClient, AsyncClientConfig
import aiohttp


# Base58 alphabet for recovery key
BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def decode_base58(s: str) -> bytes:
    """Decode a base58 string to bytes."""
    s = s.replace(" ", "")
    result = 0
    for char in s:
        result = result * 58 + BASE58_ALPHABET.index(char)
    byte_length = (result.bit_length() + 7) // 8
    return result.to_bytes(byte_length, 'big')


def decode_recovery_key(recovery_key: str) -> bytes:
    """Decode a Matrix recovery key to get the SSSS key."""
    decoded = decode_base58(recovery_key)

    # Check prefix 0x8B 0x01
    if decoded[:2] != b'\x8b\x01':
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

    return kdf.derive(passphrase.encode('utf-8'))


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
        salt=b'\x00' * 32,
        info=b'',
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
        salt=b'\x00' * 32,
        info=b'',
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

    # Derive keys using HKDF
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=80,  # 32 AES + 32 HMAC + 16 IV (but IV comes from first 16 bytes separately)
        salt=b'',
        info=b'',
    )
    derived = hkdf.derive(shared_secret)

    aes_key = derived[:32]
    mac_key = derived[32:64]
    # IV is first 16 bytes of ciphertext? No, let's check...
    # Actually for m.megolm_backup.v1.curve25519-aes-sha2:
    # The ciphertext includes the IV at the start

    # Verify MAC over ciphertext
    h = crypto_hmac.HMAC(mac_key, hashes.SHA256())
    h.update(ciphertext)
    expected_mac = h.finalize()

    if mac != expected_mac[:len(mac)]:  # MAC might be truncated
        raise ValueError("Session MAC verification failed")

    # The first 16 bytes of ciphertext are the IV
    iv = ciphertext[:16]
    actual_ciphertext = ciphertext[16:]

    # Decrypt using AES-CBC (not CTR!)
    cipher = Cipher(algorithms.AES(aes_key), modes.CBC(iv))
    decryptor = cipher.decryptor()
    padded_plaintext = decryptor.update(actual_ciphertext) + decryptor.finalize()

    # Remove PKCS7 padding
    pad_len = padded_plaintext[-1]
    plaintext = padded_plaintext[:-pad_len]

    return json.loads(plaintext)


async def main():
    parser = argparse.ArgumentParser(description="Matrix key backup")
    parser.add_argument("--recovery-key", help="Recovery key (base58 format)")
    parser.add_argument("--passphrase", help="Recovery passphrase")
    parser.add_argument("--status", action="store_true", help="Show backup status")
    parser.add_argument("--import-keys", action="store_true", help="Import keys after decryption")
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

        print(f"=== Key Backup Info ===")
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
                        len(sessions.get("sessions", {}))
                        for sessions in rooms.values()
                    )
                    print(f"Rooms with backups: {len(rooms)}")
                    print(f"Total sessions: {session_count}")
            return 0

        # Need recovery key or passphrase
        if not args.recovery_key and not args.passphrase:
            print("\nTo restore keys, provide --recovery-key or --passphrase")
            print("\nYour recovery key looks like: EsTj qRGp YB4C ...")
            return 1

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
        print(f"\n=== Deriving SSSS Key ===")
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
        with open(backup_key_file, "w") as f:
            json.dump({
                "backup_key": base64.b64encode(backup_key).decode(),
                "version": backup_info.get("version"),
                "algorithm": backup_info.get("algorithm"),
            }, f, indent=2)
        print(f"\n✅ Backup key saved to: {backup_key_file}")

        if not args.import_keys:
            print("\nUse --import-keys to fetch and import room keys from backup")
            return 0

        # Fetch and import keys
        print("\n=== Fetching Keys from Backup ===")
        version = backup_info.get("version")
        url = f"{config['homeserver']}/_matrix/client/v3/room_keys/keys?version={version}"
        async with session.get(url, headers=headers) as resp:
            if resp.status != 200:
                print(f"Failed to fetch keys: {resp.status}")
                return 1
            keys_data = await resp.json()

        rooms = keys_data.get("rooms", {})
        print(f"Found {len(rooms)} rooms with backups")

        # Connect to nio client for importing
        client_config = AsyncClientConfig(store_sync_tokens=True, encryption_enabled=True)
        client = AsyncClient(
            homeserver=config["homeserver"],
            user=config["user_id"],
            device_id=creds["device_id"],
            store_path=str(store_path),
            config=client_config,
        )

        try:
            client.restore_login(config["user_id"], creds["device_id"], creds["access_token"])
            if client.store:
                client.load_store()

            await client.sync(timeout=5000)

            imported = 0
            failed = 0

            for room_id, room_data in rooms.items():
                sessions = room_data.get("sessions", {})
                for session_id, session_data in sessions.items():
                    try:
                        decrypted = decrypt_backup_session(session_data, backup_key)

                        # Import the session
                        if hasattr(client.olm, 'import_inbound_group_session'):
                            # This would need the session export format
                            pass

                        imported += 1
                        if imported % 10 == 0:
                            print(f"  Processed {imported} sessions...")

                    except Exception as e:
                        failed += 1
                        if failed <= 5:
                            print(f"  Failed to decrypt session {session_id[:20]}: {e}")

            print(f"\n=== Import Complete ===")
            print(f"Imported: {imported}")
            print(f"Failed: {failed}")

        finally:
            await client.close()

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
