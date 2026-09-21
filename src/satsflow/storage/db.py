"""SQLite storage for SatsFlow.

Plain SQLite for now. Encryption-at-rest hooks in via SecureVault once
the caller has a password; this module stores ciphertext blobs without
caring what they contain.

Design:
  - One connection per Database instance. Caller manages lifetime.
  - `row_factory` set to sqlite3.Row so callers can access columns by name.
  - All schema creation is idempotent (CREATE TABLE IF NOT EXISTS).
  - Timestamps are Unix seconds (int), always UTC.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Self

from satsflow import config
from satsflow.storage.models import Claim, Creator, Donation

SCHEMA = """
CREATE TABLE IF NOT EXISTS creators (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    slug            TEXT NOT NULL UNIQUE,
    display_name    TEXT NOT NULL,
    bio             TEXT NOT NULL DEFAULT '',
    btc_address     TEXT,
    xmr_address     TEXT,
    password_hash   TEXT,
    created_at      INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS donations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    creator_id      INTEGER NOT NULL,
    coin            TEXT NOT NULL CHECK (coin IN ('BTC', 'XMR')),
    amount          INTEGER NOT NULL,
    usd_at_receipt  REAL,
    txid            TEXT,
    address         TEXT,
    donor_name      TEXT,
    message         TEXT,
    created_at      INTEGER NOT NULL,
    confirmed_at    INTEGER,
    FOREIGN KEY (creator_id) REFERENCES creators(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_donations_creator
    ON donations(creator_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_donations_address
    ON donations(address);

CREATE TABLE IF NOT EXISTS claims (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    donation_id     INTEGER NOT NULL,
    token           TEXT NOT NULL UNIQUE,
    claimed_at      INTEGER NOT NULL,
    FOREIGN KEY (donation_id) REFERENCES donations(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    token           TEXT NOT NULL UNIQUE,
    creator_id      INTEGER NOT NULL,
    created_at      INTEGER NOT NULL,
    expires_at      INTEGER NOT NULL,
    FOREIGN KEY (creator_id) REFERENCES creators(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(token);
"""


class StorageError(Exception):
    """Base for storage failures."""


class NotFoundError(StorageError):
    """Raised when a lookup returns no row but the caller required one."""


class DuplicateError(StorageError):
    """Raised on UNIQUE constraint violations."""


def _now() -> int:
    return int(time.time())


class Database:
    """SQLite-backed storage for SatsFlow."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else config.DB_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    # --- Lifecycle ----------------------------------------------------------

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # --- Creators -----------------------------------------------------------

    def create_creator(
        self,
        slug: str,
        display_name: str,
        bio: str = "",
        btc_address: str | None = None,
        xmr_address: str | None = None,
        password_hash: str | None = None,
    ) -> Creator:
        try:
            cur = self._conn.execute(
                """INSERT INTO creators
                   (slug, display_name, bio, btc_address, xmr_address,
                    password_hash, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (slug, display_name, bio, btc_address, xmr_address,
                 password_hash, _now()),
            )
            self._conn.commit()
        except sqlite3.IntegrityError as exc:
            raise DuplicateError(f"creator slug already exists: {slug}") from exc

        return self.get_creator(int(cur.lastrowid or 0))

    def get_creator(self, creator_id: int) -> Creator:
        row = self._conn.execute(
            "SELECT * FROM creators WHERE id = ?", (creator_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"creator {creator_id} not found")
        return self._row_to_creator(row)

    def get_creator_by_slug(self, slug: str) -> Creator:
        row = self._conn.execute(
            "SELECT * FROM creators WHERE slug = ?", (slug,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"creator slug not found: {slug}")
        return self._row_to_creator(row)

    def list_creators(self) -> list[Creator]:
        rows = self._conn.execute(
            "SELECT * FROM creators ORDER BY created_at DESC, id DESC"
        ).fetchall()
        return [self._row_to_creator(r) for r in rows]

    @staticmethod
    def _row_to_creator(row: sqlite3.Row) -> Creator:
        return Creator(
            id=row["id"],
            slug=row["slug"],
            display_name=row["display_name"],
            bio=row["bio"],
            btc_address=row["btc_address"],
            xmr_address=row["xmr_address"],
            password_hash=row["password_hash"],
            created_at=row["created_at"],
        )

    # --- Donations ----------------------------------------------------------

    def create_donation(
        self,
        creator_id: int,
        coin: str,
        amount: int,
        usd_at_receipt: float | None = None,
        txid: str | None = None,
        address: str | None = None,
        donor_name: str | None = None,
        message: str | None = None,
        confirmed_at: int | None = None,
    ) -> Donation:
        if coin not in ("BTC", "XMR"):
            raise StorageError(f"unsupported coin: {coin}")
        if amount < 0:
            raise StorageError("amount must be non-negative")

        cur = self._conn.execute(
            """INSERT INTO donations
               (creator_id, coin, amount, usd_at_receipt, txid, address,
                donor_name, message, created_at, confirmed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (creator_id, coin, amount, usd_at_receipt, txid, address,
             donor_name, message, _now(), confirmed_at),
        )
        self._conn.commit()
        return self.get_donation(int(cur.lastrowid or 0))

    def get_donation(self, donation_id: int) -> Donation:
        row = self._conn.execute(
            "SELECT * FROM donations WHERE id = ?", (donation_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"donation {donation_id} not found")
        return self._row_to_donation(row)

    def list_donations(
        self, creator_id: int, limit: int = 50, offset: int = 0
    ) -> list[Donation]:
        rows = self._conn.execute(
            """SELECT * FROM donations
               WHERE creator_id = ?
               ORDER BY created_at DESC
               LIMIT ? OFFSET ?""",
            (creator_id, limit, offset),
        ).fetchall()
        return [self._row_to_donation(r) for r in rows]

    def confirm_donation(self, donation_id: int, txid: str | None = None) -> Donation:
        self._conn.execute(
            """UPDATE donations
               SET confirmed_at = ?, txid = COALESCE(?, txid)
               WHERE id = ?""",
            (_now(), txid, donation_id),
        )
        self._conn.commit()
        return self.get_donation(donation_id)

    def list_donations_since(
        self, creator_id: int, since_ts: int, limit: int = 500
    ) -> list[Donation]:
        """All donations for a creator newer than since_ts (Unix seconds)."""
        rows = self._conn.execute(
            """SELECT * FROM donations
               WHERE creator_id = ? AND created_at >= ?
               ORDER BY created_at DESC, id DESC
               LIMIT ?""",
            (creator_id, since_ts, limit),
        ).fetchall()
        return [self._row_to_donation(r) for r in rows]

    @staticmethod
    def _row_to_donation(row: sqlite3.Row) -> Donation:
        return Donation(
            id=row["id"],
            creator_id=row["creator_id"],
            coin=row["coin"],
            amount=row["amount"],
            usd_at_receipt=row["usd_at_receipt"],
            txid=row["txid"],
            address=row["address"],
            donor_name=row["donor_name"],
            message=row["message"],
            created_at=row["created_at"],
            confirmed_at=row["confirmed_at"],
        )

    # --- Claims -------------------------------------------------------------

    def create_claim(self, donation_id: int, token: str) -> Claim:
        try:
            cur = self._conn.execute(
                "INSERT INTO claims (donation_id, token, claimed_at) VALUES (?, ?, ?)",
                (donation_id, token, _now()),
            )
            self._conn.commit()
        except sqlite3.IntegrityError as exc:
            raise DuplicateError(f"claim token already exists: {token}") from exc

        return self.get_claim(int(cur.lastrowid or 0))

    def get_claim(self, claim_id: int) -> Claim:
        row = self._conn.execute(
            "SELECT * FROM claims WHERE id = ?", (claim_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"claim {claim_id} not found")
        return self._row_to_claim(row)

    def get_claim_by_token(self, token: str) -> Claim:
        row = self._conn.execute(
            "SELECT * FROM claims WHERE token = ?", (token,)
        ).fetchone()
        if row is None:
            raise NotFoundError("claim token not found")
        return self._row_to_claim(row)

    @staticmethod
    def _row_to_claim(row: sqlite3.Row) -> Claim:
        return Claim(
            id=row["id"],
            donation_id=row["donation_id"],
            token=row["token"],
            claimed_at=row["claimed_at"],
        )

    # --- Sessions -----------------------------------------------------------

    def create_session(
        self, creator_id: int, token: str, ttl_seconds: int = 30 * 24 * 3600
    ) -> int:
        """Create a session row. Returns the session id."""
        now = _now()
        cur = self._conn.execute(
            """INSERT INTO sessions (token, creator_id, created_at, expires_at)
               VALUES (?, ?, ?, ?)""",
            (token, creator_id, now, now + ttl_seconds),
        )
        self._conn.commit()
        if cur.lastrowid is None:
            raise StorageError("insert did not return a rowid")
        return int(cur.lastrowid)

    def get_session_creator(self, token: str) -> Creator | None:
        """Return the creator for a live session, or None if expired/unknown."""
        row = self._conn.execute(
            "SELECT * FROM sessions WHERE token = ?", (token,)
        ).fetchone()
        if row is None:
            return None
        if row["expires_at"] < _now():
            self.delete_session(token)
            return None
        try:
            return self.get_creator(int(row["creator_id"]))
        except NotFoundError:
            return None

    def delete_session(self, token: str) -> None:
        self._conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        self._conn.commit()

    def purge_expired_sessions(self) -> int:
        """Delete expired sessions. Returns how many were removed."""
        cur = self._conn.execute(
            "DELETE FROM sessions WHERE expires_at < ?", (_now(),)
        )
        self._conn.commit()
        return cur.rowcount or 0
