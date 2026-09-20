"""Argon2id password hashing, tuned for Termux / mobile.

Argon2id is the current recommendation (Password Hashing Competition winner).
Parameters here are deliberately lighter on memory than the desktop default
(64 MiB) because Termux devices often have limited RAM. We compensate by
raising time_cost, which keeps the work factor high while staying under
a mobile memory ceiling.

Never store, log, or transmit plaintext passwords. Never store the hash
without its salt — argon2-cffi embeds the salt in the encoded hash string.
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from argon2.low_level import Type

# Tuned for Termux. Desktop defaults are time_cost=3, memory_cost=65536.
# Lower memory, higher iterations — same approximate work, less RAM peak.
_TIME_COST = 4          # iterations
_MEMORY_COST = 32768    # 32 MiB
_PARALLELISM = 2        # mobile CPUs usually 4-8 cores; 2 lanes is safe

_hasher = PasswordHasher(
    time_cost=_TIME_COST,
    memory_cost=_MEMORY_COST,
    parallelism=_PARALLELISM,
    hash_len=32,
    salt_len=16,
    type=Type.ID,       # Argon2id — hybrid, resists side-channel + GPU
)


def hash_password(password: str) -> str:
    """Return an encoded Argon2id hash string (includes salt + params)."""
    if not isinstance(password, str) or not password:
        raise ValueError("password must be a non-empty string")
    return _hasher.hash(password)


def verify_password(stored_hash: str, password: str) -> bool:
    """Constant-time verify. Returns True/False, never raises on mismatch."""
    try:
        return _hasher.verify(stored_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(stored_hash: str) -> bool:
    """True if the stored hash used weaker params than current defaults."""
    try:
        return _hasher.check_needs_rehash(stored_hash)
    except InvalidHashError:
        return True
