"""AES-256-GCM vault + Argon2id-derived keys.

Security model:
  - User's password never stored anywhere.
  - A random 16-byte salt is generated once per vault and stored alongside
    the ciphertext (salt is not secret; it just prevents rainbow tables).
  - Argon2id derives a 32-byte key from (password, salt). That key lives
    in memory only while the vault is unlocked.
  - All data encrypted with AES-256-GCM (authenticated encryption — any
    tampering with ciphertext, nonce, or AAD causes decryption to fail).
  - Nonces are 12 random bytes per encryption. Never reused. Stored with
    ciphertext.

Wire format for an encrypted blob (base64 of):
    [1 byte version][12 bytes nonce][ciphertext + 16-byte GCM tag]

Lock semantics:
  - SecureVault.lock() zeroes the key bytes, then sets _key to None.
  - None is the sentinel for "locked". Any encrypt/decrypt on a locked
    vault raises VaultError instead of silently using a zeroed key.
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass

from argon2.low_level import hash_secret_raw, Type
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_VERSION = 1
_SALT_LEN = 16
_NONCE_LEN = 12
_KEY_LEN = 32

# Must match passwords.py cost profile so both use the same tuning philosophy.
_KDF_TIME_COST = 4
_KDF_MEMORY_COST = 32768
_KDF_PARALLELISM = 2


class VaultError(Exception):
    """Base for vault failures."""


class WrongPasswordError(VaultError):
    """Raised when the derived key fails to authenticate the ciphertext."""


class TamperedDataError(VaultError):
    """Raised when GCM authentication fails on otherwise-valid-looking data."""


def derive_key(password: str, salt: bytes) -> bytes:
    """Argon2id KDF → 32-byte AES key. Deterministic for a given (password, salt)."""
    if not isinstance(password, str) or not password:
        raise ValueError("password must be a non-empty string")
    if len(salt) != _SALT_LEN:
        raise ValueError(f"salt must be {_SALT_LEN} bytes")
    return hash_secret_raw(
        secret=password.encode("utf-8"),
        salt=salt,
        time_cost=_KDF_TIME_COST,
        memory_cost=_KDF_MEMORY_COST,
        parallelism=_KDF_PARALLELISM,
        hash_len=_KEY_LEN,
        type=Type.ID,
    )


def new_salt() -> bytes:
    return os.urandom(_SALT_LEN)


def encrypt(key: bytes, plaintext: bytes, aad: bytes | None = None) -> bytes:
    """Encrypt with AES-256-GCM. Returns versioned blob: version||nonce||ct."""
    if len(key) != _KEY_LEN:
        raise ValueError(f"key must be {_KEY_LEN} bytes")
    nonce = os.urandom(_NONCE_LEN)
    aes = AESGCM(key)
    ct = aes.encrypt(nonce, plaintext, aad)
    return bytes([_VERSION]) + nonce + ct


def decrypt(key: bytes, blob: bytes, aad: bytes | None = None) -> bytes:
    """Decrypt a blob produced by encrypt(). Raises on any tampering."""
    if len(key) != _KEY_LEN:
        raise ValueError(f"key must be {_KEY_LEN} bytes")
    if len(blob) < 1 + _NONCE_LEN + 16:
        raise TamperedDataError("blob too short")
    if blob[0] != _VERSION:
        raise TamperedDataError(f"unsupported version {blob[0]}")

    nonce = blob[1 : 1 + _NONCE_LEN]
    ct = blob[1 + _NONCE_LEN :]
    aes = AESGCM(key)
    try:
        return aes.decrypt(nonce, ct, aad)
    except InvalidTag as exc:
        raise TamperedDataError("authentication failed") from exc


def encrypt_b64(key: bytes, plaintext: bytes, aad: bytes | None = None) -> str:
    return base64.b64encode(encrypt(key, plaintext, aad)).decode("ascii")


def decrypt_b64(key: bytes, blob_b64: str, aad: bytes | None = None) -> bytes:
    try:
        blob = base64.b64decode(blob_b64, validate=True)
    except Exception as exc:
        raise TamperedDataError("invalid base64") from exc
    return decrypt(key, blob, aad)


@dataclass
class SecureVault:
    """In-memory vault holding the derived key while unlocked.

    Usage:
        v = SecureVault.create(password)          # new vault, fresh salt
        v = SecureVault.unlock(password, salt)    # reopen existing vault
        blob = v.encrypt(b"secret data")
        v.lock()

    Lock semantics:
        _key is None  -> vault is locked. Any crypto op raises VaultError.
        _key is bytes -> vault is unlocked.

    Nothing is persisted by this class. Persistence (salt + blobs) is the
    caller's job — see storage/db.py.
    """

    _key: bytes | None
    _salt: bytes

    @classmethod
    def create(cls, password: str) -> "SecureVault":
        """Fresh vault: generate a new salt and derive the key."""
        salt = new_salt()
        key = derive_key(password, salt)
        return cls(_key=key, _salt=salt)

    @classmethod
    def unlock(cls, password: str, salt: bytes) -> "SecureVault":
        """Reopen an existing vault from its stored salt."""
        key = derive_key(password, salt)
        return cls(_key=key, _salt=salt)

    @property
    def salt(self) -> bytes:
        return self._salt

    @property
    def locked(self) -> bool:
        return self._key is None

    def _require_key(self) -> bytes:
        if self._key is None:
            raise VaultError("vault is locked")
        return self._key

    def encrypt(self, plaintext: bytes, aad: bytes | None = None) -> bytes:
        return encrypt(self._require_key(), plaintext, aad)

    def decrypt(self, blob: bytes, aad: bytes | None = None) -> bytes:
        return decrypt(self._require_key(), blob, aad)

    def encrypt_b64(self, plaintext: bytes, aad: bytes | None = None) -> str:
        return encrypt_b64(self._require_key(), plaintext, aad)

    def decrypt_b64(self, blob_b64: str, aad: bytes | None = None) -> bytes:
        return decrypt_b64(self._require_key(), blob_b64, aad)

    def lock(self) -> None:
        """Zero the key bytes in memory, then drop the reference.

        Sets _key to None so any subsequent crypto op raises VaultError.
        Idempotent — calling lock() twice is safe.
        """
        if self._key is not None:
            # Best-effort overwrite. Python may have copies elsewhere;
            # this only guarantees the attribute itself is zeroed.
            self._key = b"\x00" * len(self._key)
            self._key = None

    def __repr__(self) -> str:
        return f"<SecureVault locked={'yes' if self._key is None else 'no'}>"
