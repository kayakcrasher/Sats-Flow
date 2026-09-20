"""Tests for security.crypto and security.passwords.

Fast by design: use low-cost Argon2 params in tests via monkeypatch so the
suite runs in seconds, not minutes.
"""

from __future__ import annotations

import pytest

from satsflow.security import crypto, passwords

# ---------------------------------------------------------------------------
# passwords.py
# ---------------------------------------------------------------------------

class TestPasswordHashing:
    def test_hash_and_verify_roundtrip(self):
        h = passwords.hash_password("correct horse battery staple")
        assert passwords.verify_password(h, "correct horse battery staple") is True

    def test_verify_rejects_wrong_password(self):
        h = passwords.hash_password("hunter2")
        assert passwords.verify_password(h, "hunter3") is False

    def test_verify_handles_garbage_hash(self):
        assert passwords.verify_password("not-a-hash", "anything") is False

    def test_hash_is_salted(self):
        h1 = passwords.hash_password("same")
        h2 = passwords.hash_password("same")
        assert h1 != h2  # unique salts

    def test_empty_password_rejected(self):
        with pytest.raises(ValueError):
            passwords.hash_password("")

    def test_needs_rehash_false_for_current_params(self):
        h = passwords.hash_password("x")
        assert passwords.needs_rehash(h) is False

    def test_needs_rehash_true_for_garbage(self):
        assert passwords.needs_rehash("garbage") is True


# ---------------------------------------------------------------------------
# crypto.py — use tiny Argon2 params so tests are fast
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _fast_kdf(monkeypatch):
    """Drop Argon2 cost so tests run in milliseconds, not seconds."""
    monkeypatch.setattr(crypto, "_KDF_TIME_COST", 1)
    monkeypatch.setattr(crypto, "_KDF_MEMORY_COST", 8)   # KiB — absurdly low, test-only
    monkeypatch.setattr(crypto, "_KDF_PARALLELISM", 1)


class TestKeyDerivation:
    def test_same_password_same_salt_same_key(self):
        salt = crypto.new_salt()
        k1 = crypto.derive_key("pw", salt)
        k2 = crypto.derive_key("pw", salt)
        assert k1 == k2
        assert len(k1) == 32

    def test_different_salt_different_key(self):
        k1 = crypto.derive_key("pw", crypto.new_salt())
        k2 = crypto.derive_key("pw", crypto.new_salt())
        assert k1 != k2

    def test_different_password_different_key(self):
        salt = crypto.new_salt()
        k1 = crypto.derive_key("pw1", salt)
        k2 = crypto.derive_key("pw2", salt)
        assert k1 != k2

    def test_bad_salt_length(self):
        with pytest.raises(ValueError):
            crypto.derive_key("pw", b"tooshort")


class TestAESGCM:
    def _key(self) -> bytes:
        return crypto.derive_key("pw", crypto.new_salt())

    def test_encrypt_decrypt_roundtrip(self):
        key = self._key()
        blob = crypto.encrypt(key, b"hello satsflow")
        assert crypto.decrypt(key, blob) == b"hello satsflow"

    def test_nonce_is_random(self):
        key = self._key()
        a = crypto.encrypt(key, b"same plaintext")
        b = crypto.encrypt(key, b"same plaintext")
        assert a != b  # different nonces -> different ciphertext

    def test_tampered_ciphertext_raises(self):
        key = self._key()
        blob = bytearray(crypto.encrypt(key, b"data"))
        blob[-1] ^= 0x01  # flip a bit in the tag/ciphertext
        with pytest.raises(crypto.TamperedDataError):
            crypto.decrypt(key, bytes(blob))

    def test_tampered_nonce_raises(self):
        key = self._key()
        blob = bytearray(crypto.encrypt(key, b"data"))
        blob[1] ^= 0xFF  # flip a bit in the nonce
        with pytest.raises(crypto.TamperedDataError):
            crypto.decrypt(key, bytes(blob))

    def test_wrong_key_raises(self):
        blob = crypto.encrypt(self._key(), b"data")
        with pytest.raises(crypto.TamperedDataError):
            crypto.decrypt(self._key(), blob)

    def test_aad_mismatch_raises(self):
        key = self._key()
        blob = crypto.encrypt(key, b"data", aad=b"ctx-A")
        with pytest.raises(crypto.TamperedDataError):
            crypto.decrypt(key, blob, aad=b"ctx-B")

    def test_aad_match_succeeds(self):
        key = self._key()
        blob = crypto.encrypt(key, b"data", aad=b"ctx-A")
        assert crypto.decrypt(key, blob, aad=b"ctx-A") == b"data"

    def test_blob_too_short_rejected(self):
        key = self._key()
        with pytest.raises(crypto.TamperedDataError):
            crypto.decrypt(key, b"\x01\x00")

    def test_bad_version_rejected(self):
        key = self._key()
        blob = bytearray(crypto.encrypt(key, b"x"))
        blob[0] = 99
        with pytest.raises(crypto.TamperedDataError):
            crypto.decrypt(key, bytes(blob))

    def test_b64_roundtrip(self):
        key = self._key()
        s = crypto.encrypt_b64(key, b"b64 test")
        assert crypto.decrypt_b64(key, s) == b"b64 test"

    def test_b64_invalid_input_raises(self):
        key = self._key()
        with pytest.raises(crypto.TamperedDataError):
            crypto.decrypt_b64(key, "not!!valid!!base64!!")


class TestSecureVault:
    def test_create_and_use(self):
        v = crypto.SecureVault.create("pw")
        blob = v.encrypt(b"secret")
        assert v.decrypt(blob) == b"secret"

    def test_unlock_with_correct_password(self):
        v1 = crypto.SecureVault.create("pw")
        salt = v1.salt
        blob = v1.encrypt(b"data")
        v2 = crypto.SecureVault.unlock("pw", salt)
        assert v2.decrypt(blob) == b"data"

    def test_unlock_with_wrong_password_fails_on_decrypt(self):
        v1 = crypto.SecureVault.create("right")
        salt = v1.salt
        blob = v1.encrypt(b"data")
        v2 = crypto.SecureVault.unlock("wrong", salt)
        with pytest.raises(crypto.TamperedDataError):
            v2.decrypt(blob)

    def test_salt_is_stable_across_unlocks(self):
        v = crypto.SecureVault.create("pw")
        assert v.salt == crypto.SecureVault.unlock("pw", v.salt).salt

    # --- lock semantics ---------------------------------------------------

    def test_initially_unlocked(self):
        v = crypto.SecureVault.create("pw")
        assert v.locked is False
        assert "locked=no" in repr(v)

    def test_lock_wipes_key(self):
        v = crypto.SecureVault.create("pw")
        v.lock()
        assert v.locked is True
        assert "locked=yes" in repr(v)

    def test_use_after_lock_raises(self):
        v = crypto.SecureVault.create("pw")
        v.lock()
        with pytest.raises(crypto.VaultError):
            v.encrypt(b"data")

    def test_decrypt_after_lock_raises(self):
        v = crypto.SecureVault.create("pw")
        blob = v.encrypt(b"data")
        v.lock()
        with pytest.raises(crypto.VaultError):
            v.decrypt(blob)

    def test_double_lock_is_safe(self):
        v = crypto.SecureVault.create("pw")
        v.lock()
        v.lock()  # second lock shouldn't crash
        assert v.locked is True

    def test_encrypt_b64_after_lock_raises(self):
        v = crypto.SecureVault.create("pw")
        v.lock()
        with pytest.raises(crypto.VaultError):
            v.encrypt_b64(b"data")
