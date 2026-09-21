"""Tests for storage.db and storage.models."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from satsflow.storage.db import (
    Database,
    DuplicateError,
    NotFoundError,
    StorageError,
)


@pytest.fixture
def db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    d = Database(path)
    yield d
    d.close()
    Path(path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Creators
# ---------------------------------------------------------------------------

class TestCreators:
    def test_create_and_get(self, db):
        c = db.create_creator("alice", "Alice", bio="hello")
        assert c.id is not None
        assert c.slug == "alice"
        assert c.display_name == "Alice"
        assert c.bio == "hello"
        assert c.created_at > 0

        fetched = db.get_creator(c.id)
        assert fetched.slug == "alice"

    def test_get_by_slug(self, db):
        db.create_creator("bob", "Bob")
        c = db.get_creator_by_slug("bob")
        assert c.display_name == "Bob"

    def test_duplicate_slug_rejected(self, db):
        db.create_creator("alice", "Alice")
        with pytest.raises(DuplicateError, match="already exists"):
            db.create_creator("alice", "Other Alice")

    def test_unknown_id_raises(self, db):
        with pytest.raises(NotFoundError, match="not found"):
            db.get_creator(9999)

    def test_unknown_slug_raises(self, db):
        with pytest.raises(NotFoundError, match="not found"):
            db.get_creator_by_slug("nobody")

    def test_list_creators(self, db):
        db.create_creator("a", "A")
        db.create_creator("b", "B")
        db.create_creator("c", "C")
        creators = db.list_creators()
        assert len(creators) == 3
        # newest first
        assert creators[0].slug == "c"

    def test_optional_fields_default_none(self, db):
        c = db.create_creator("x", "X")
        assert c.btc_address is None
        assert c.xmr_address is None
        assert c.password_hash is None

    def test_password_hash_stored(self, db):
        c = db.create_creator("x", "X", password_hash="argon2hash")
        fetched = db.get_creator(c.id)
        assert fetched.password_hash == "argon2hash"


# ---------------------------------------------------------------------------
# Donations
# ---------------------------------------------------------------------------

class TestDonations:
    def test_create_and_get(self, db):
        c = db.create_creator("alice", "Alice")
        d = db.create_donation(
            c.id, "BTC", 100_000,
            usd_at_receipt=42.50,
            donor_name="bob",
            message="great work!",
        )
        assert d.id is not None
        assert d.creator_id == c.id
        assert d.coin == "BTC"
        assert d.amount == 100_000
        assert d.usd_at_receipt == 42.50
        assert d.donor_name == "bob"
        assert d.message == "great work!"
        assert d.confirmed_at is None

    def test_xmr_donation(self, db):
        c = db.create_creator("alice", "Alice")
        d = db.create_donation(c.id, "XMR", 1_000_000_000_000)
        assert d.coin == "XMR"
        assert d.amount == 1_000_000_000_000

    def test_invalid_coin_rejected(self, db):
        c = db.create_creator("alice", "Alice")
        with pytest.raises(StorageError, match="unsupported coin"):
            db.create_donation(c.id, "DOGE", 100)

    def test_negative_amount_rejected(self, db):
        c = db.create_creator("alice", "Alice")
        with pytest.raises(StorageError, match="non-negative"):
            db.create_donation(c.id, "BTC", -1)

    def test_list_donations_for_creator(self, db):
        c = db.create_creator("alice", "Alice")
        db.create_donation(c.id, "BTC", 100)
        db.create_donation(c.id, "BTC", 200)
        db.create_donation(c.id, "XMR", 300)
        donations = db.list_donations(c.id)
        assert len(donations) == 3

    def test_list_donations_empty(self, db):
        c = db.create_creator("alice", "Alice")
        assert db.list_donations(c.id) == []

    def test_list_donations_limit_offset(self, db):
        c = db.create_creator("alice", "Alice")
        for i in range(5):
            db.create_donation(c.id, "BTC", (i + 1) * 100)
        page1 = db.list_donations(c.id, limit=2, offset=0)
        page2 = db.list_donations(c.id, limit=2, offset=2)
        assert len(page1) == 2
        assert len(page2) == 2
        # Different rows
        assert page1[0].id != page2[0].id

    def test_donations_isolated_by_creator(self, db):
        alice = db.create_creator("alice", "Alice")
        bob = db.create_creator("bob", "Bob")
        db.create_donation(alice.id, "BTC", 100)
        db.create_donation(bob.id, "BTC", 200)
        assert len(db.list_donations(alice.id)) == 1
        assert db.list_donations(alice.id)[0].amount == 100

    def test_confirm_donation(self, db):
        c = db.create_creator("alice", "Alice")
        d = db.create_donation(c.id, "BTC", 100)
        assert d.confirmed_at is None

        confirmed = db.confirm_donation(d.id, txid="abc123")
        assert confirmed.confirmed_at is not None
        assert confirmed.txid == "abc123"

    def test_confirm_preserves_existing_txid(self, db):
        c = db.create_creator("alice", "Alice")
        d = db.create_donation(c.id, "BTC", 100, txid="original")
        confirmed = db.confirm_donation(d.id)  # no txid passed
        assert confirmed.txid == "original"

    def test_unknown_donation_raises(self, db):
        with pytest.raises(NotFoundError, match="not found"):
            db.get_donation(9999)


# ---------------------------------------------------------------------------
# Claims
# ---------------------------------------------------------------------------

class TestClaims:
    def test_create_and_get(self, db):
        c = db.create_creator("alice", "Alice")
        d = db.create_donation(c.id, "BTC", 100)
        claim = db.create_claim(d.id, token="tok-abc")
        assert claim.id is not None
        assert claim.donation_id == d.id
        assert claim.token == "tok-abc"
        assert claim.claimed_at > 0

    def test_get_by_token(self, db):
        c = db.create_creator("alice", "Alice")
        d = db.create_donation(c.id, "BTC", 100)
        db.create_claim(d.id, token="tok-abc")
        claim = db.get_claim_by_token("tok-abc")
        assert claim.donation_id == d.id

    def test_duplicate_token_rejected(self, db):
        c = db.create_creator("alice", "Alice")
        d = db.create_donation(c.id, "BTC", 100)
        db.create_claim(d.id, token="tok-abc")
        with pytest.raises(DuplicateError, match="already exists"):
            db.create_claim(d.id, token="tok-abc")

    def test_unknown_token_raises(self, db):
        with pytest.raises(NotFoundError, match="not found"):
            db.get_claim_by_token("nope")

    def test_unknown_claim_id_raises(self, db):
        with pytest.raises(NotFoundError, match="not found"):
            db.get_claim(9999)


# ---------------------------------------------------------------------------
# Schema / lifecycle
# ---------------------------------------------------------------------------

class TestLifecycle:
    def test_reopen_persists_data(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            db1 = Database(path)
            c = db1.create_creator("alice", "Alice")
            db1.close()

            db2 = Database(path)
            fetched = db2.get_creator_by_slug("alice")
            assert fetched.id == c.id
            db2.close()
        finally:
            Path(path).unlink(missing_ok=True)

    def test_context_manager(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            with Database(path) as db:
                db.create_creator("alice", "Alice")
            # Connection closed here; no exception = pass
        finally:
            Path(path).unlink(missing_ok=True)

    def test_foreign_key_cascade(self, db):
        c = db.create_creator("alice", "Alice")
        d = db.create_donation(c.id, "BTC", 100)
        db.create_claim(d.id, token="tok-abc")

        # Delete the creator -> donations and claims cascade
        db._conn.execute("DELETE FROM creators WHERE id = ?", (c.id,))
        db._conn.commit()

        with pytest.raises(NotFoundError):
            db.get_donation(d.id)
