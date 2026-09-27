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
from satsflow.storage.models import Claim, Donation, User

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    slug            TEXT NOT NULL UNIQUE,
    display_name    TEXT NOT NULL,
    bio             TEXT NOT NULL DEFAULT '',
    btc_address     TEXT,
    xmr_address     TEXT,
    btc_xpub        TEXT,
    next_btc_index  INTEGER NOT NULL DEFAULT 0,
    fee_override    REAL,
    fee_balance_sats INTEGER NOT NULL DEFAULT 0,
    is_creator      INTEGER NOT NULL DEFAULT 1,
    password_hash   TEXT,
    created_at      INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS donations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL,
    coin            TEXT NOT NULL CHECK (coin IN ('BTC', 'XMR')),
    amount          INTEGER NOT NULL,
    usd_at_receipt  REAL,
    txid            TEXT,
    address         TEXT,
    donor_name      TEXT,
    message         TEXT,
    created_at      INTEGER NOT NULL,
    confirmed_at    INTEGER,
    platform_fee_sats INTEGER NOT NULL DEFAULT 0,
    fee_percent_at_creation REAL NOT NULL DEFAULT 0,
    pinned          INTEGER NOT NULL DEFAULT 0,
    read_at         INTEGER,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_donations_user
    ON donations(user_id, created_at DESC);

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
    user_id      INTEGER NOT NULL,
    created_at      INTEGER NOT NULL,
    expires_at      INTEGER NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(token);

CREATE TABLE IF NOT EXISTS fee_settlements (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL,
    amount_sats     INTEGER NOT NULL,
    txid            TEXT NOT NULL,
    address         TEXT,
    created_at      INTEGER NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
"""


def _migrate(conn: sqlite3.Connection) -> None:
    """Add columns that may be missing on older databases."""
    cur = conn.execute("PRAGMA table_info(donations)")
    cols = {row[1] for row in cur.fetchall()}
    if "pinned" not in cols:
        conn.execute("ALTER TABLE donations ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0")
    if "read_at" not in cols:
        conn.execute("ALTER TABLE donations ADD COLUMN read_at INTEGER")
    # Index depends on the columns above being present.
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_donations_pinned "
        "ON donations(user_id, pinned DESC, created_at DESC)"
    )
    # User columns added for per-user xpub + fee override
    cur = conn.execute("PRAGMA table_info(users)")
    user_cols = {row[1] for row in cur.fetchall()}
    if "btc_xpub" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN btc_xpub TEXT")
    if "next_btc_index" not in user_cols:
        conn.execute(
            "ALTER TABLE users ADD COLUMN next_btc_index INTEGER NOT NULL DEFAULT 0"
        )
    if "fee_override" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN fee_override REAL")
    if "fee_balance_sats" not in user_cols:
        conn.execute(
            "ALTER TABLE users ADD COLUMN fee_balance_sats INTEGER NOT NULL DEFAULT 0"
        )
    cur = conn.execute("PRAGMA table_info(donations)")
    donation_cols = {row[1] for row in cur.fetchall()}
    if "platform_fee_sats" not in donation_cols:
        conn.execute(
            "ALTER TABLE donations ADD COLUMN platform_fee_sats INTEGER NOT NULL DEFAULT 0"
        )
    if "fee_percent_at_creation" not in donation_cols:
        conn.execute(
            "ALTER TABLE donations ADD COLUMN fee_percent_at_creation REAL NOT NULL DEFAULT 0"
        )
    conn.commit()


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
        _migrate(self._conn)
        self._conn.commit()

    # --- Lifecycle ----------------------------------------------------------

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # --- Users -----------------------------------------------------------

    def create_user(
        self,
        slug: str,
        display_name: str,
        bio: str = "",
        btc_address: str | None = None,
        xmr_address: str | None = None,
        password_hash: str | None = None,
        is_creator: bool = True,
    ) -> User:
        try:
            cur = self._conn.execute(
                """INSERT INTO users
                   (slug, display_name, bio, btc_address, xmr_address,
                    password_hash, is_creator, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (slug, display_name, bio, btc_address, xmr_address,
                 password_hash, 1 if is_creator else 0, _now()),
            )
            self._conn.commit()
        except sqlite3.IntegrityError as exc:
            raise DuplicateError(f"user slug already exists: {slug}") from exc

        return self.get_user(int(cur.lastrowid or 0))

    def get_user(self, user_id: int) -> User:
        row = self._conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"user {user_id} not found")
        return self._row_to_user(row)

    def get_user_by_slug(self, slug: str) -> User:
        row = self._conn.execute(
            "SELECT * FROM users WHERE slug = ?", (slug,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"user slug not found: {slug}")
        return self._row_to_user(row)

    def list_users(self) -> list[User]:
        rows = self._conn.execute(
            "SELECT * FROM users ORDER BY created_at DESC, id DESC"
        ).fetchall()
        return [self._row_to_user(r) for r in rows]

    @staticmethod
    def _row_to_user(row: sqlite3.Row) -> User:
        return User(
            id=row["id"],
            slug=row["slug"],
            display_name=row["display_name"],
            bio=row["bio"],
            btc_address=row["btc_address"],
            xmr_address=row["xmr_address"],
            btc_xpub=row["btc_xpub"],
            next_btc_index=int(row["next_btc_index"] or 0),
            fee_override=row["fee_override"],
            fee_balance_sats=int(row["fee_balance_sats"] or 0),
            is_creator=bool(row["is_creator"]),
            password_hash=row["password_hash"],
            created_at=row["created_at"],
        )

    # --- Donations ----------------------------------------------------------

    def create_donation(
        self,
        user_id: int,
        coin: str,
        amount: int,
        usd_at_receipt: float | None = None,
        txid: str | None = None,
        address: str | None = None,
        donor_name: str | None = None,
        message: str | None = None,
        confirmed_at: int | None = None,
        platform_fee_sats: int = 0,
        fee_percent_at_creation: float = 0.0,
    ) -> Donation:
        if coin not in ("BTC", "XMR"):
            raise StorageError(f"unsupported coin: {coin}")
        if amount < 0:
            raise StorageError("amount must be non-negative")

        cur = self._conn.execute(
            """INSERT INTO donations
               (user_id, coin, amount, usd_at_receipt, txid, address,
                donor_name, message, created_at, confirmed_at,
                platform_fee_sats, fee_percent_at_creation)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, coin, amount, usd_at_receipt, txid, address,
             donor_name, message, _now(), confirmed_at,
             platform_fee_sats, fee_percent_at_creation),
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
        self, user_id: int, limit: int = 50, offset: int = 0
    ) -> list[Donation]:
        rows = self._conn.execute(
            """SELECT * FROM donations
               WHERE user_id = ?
               ORDER BY created_at DESC
               LIMIT ? OFFSET ?""",
            (user_id, limit, offset),
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
        self, user_id: int, since_ts: int, limit: int = 500
    ) -> list[Donation]:
        """All donations for a user newer than since_ts (Unix seconds)."""
        rows = self._conn.execute(
            """SELECT * FROM donations
               WHERE user_id = ? AND created_at >= ?
               ORDER BY created_at DESC, id DESC
               LIMIT ?""",
            (user_id, since_ts, limit),
        ).fetchall()
        return [self._row_to_donation(r) for r in rows]

    @staticmethod
    def _row_to_donation(row: sqlite3.Row) -> Donation:
        return Donation(
            id=row["id"],
            user_id=row["user_id"],
            coin=row["coin"],
            amount=row["amount"],
            usd_at_receipt=row["usd_at_receipt"],
            txid=row["txid"],
            address=row["address"],
            donor_name=row["donor_name"],
            message=row["message"],
            created_at=row["created_at"],
            confirmed_at=row["confirmed_at"],
            platform_fee_sats=int(row["platform_fee_sats"] or 0),
            fee_percent_at_creation=float(row["fee_percent_at_creation"] or 0.0),
            pinned=bool(row["pinned"]),
            read_at=row["read_at"],
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
        self, user_id: int, token: str, ttl_seconds: int = 30 * 24 * 3600
    ) -> int:
        """Create a session row. Returns the session id."""
        now = _now()
        cur = self._conn.execute(
            """INSERT INTO sessions (token, user_id, created_at, expires_at)
               VALUES (?, ?, ?, ?)""",
            (token, user_id, now, now + ttl_seconds),
        )
        self._conn.commit()
        if cur.lastrowid is None:
            raise StorageError("insert did not return a rowid")
        return int(cur.lastrowid)

    def get_session_user(self, token: str) -> User | None:
        """Return the user for a live session, or None if expired/unknown."""
        row = self._conn.execute(
            "SELECT * FROM sessions WHERE token = ?", (token,)
        ).fetchone()
        if row is None:
            return None
        if row["expires_at"] < _now():
            self.delete_session(token)
            return None
        try:
            return self.get_user(int(row["user_id"]))
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

    def list_donations_since_filtered(
        self,
        user_id: int,
        since_ts: int,
        min_amount: int = 0,
        limit: int = 500,
    ) -> list[Donation]:
        """Same as list_donations_since, but only donations >= min_amount."""
        rows = self._conn.execute(
            """SELECT * FROM donations
               WHERE user_id = ? AND created_at >= ? AND amount >= ?
               ORDER BY pinned DESC, created_at DESC, id DESC
               LIMIT ?""",
            (user_id, since_ts, min_amount, limit),
        ).fetchall()
        return [self._row_to_donation(r) for r in rows]

    def set_pinned(self, donation_id: int, pinned: bool) -> Donation:
        self._conn.execute(
            "UPDATE donations SET pinned = ? WHERE id = ?",
            (1 if pinned else 0, donation_id),
        )
        self._conn.commit()
        return self.get_donation(donation_id)

    def mark_read(self, donation_id: int) -> Donation:
        self._conn.execute(
            "UPDATE donations SET read_at = ? WHERE id = ? AND read_at IS NULL",
            (_now(), donation_id),
        )
        self._conn.commit()
        return self.get_donation(donation_id)

    def count_unread(self, user_id: int) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM donations WHERE user_id = ? AND read_at IS NULL",
            (user_id,),
        ).fetchone()
        return int(row["n"]) if row else 0

    def set_user_xpub(self, user_id: int, xpub: str | None) -> User:
        """Set or clear a user's BTC xpub (watch-only)."""
        self._conn.execute(
            "UPDATE users SET btc_xpub = ? WHERE id = ?",
            (xpub, user_id),
        )
        self._conn.commit()
        return self.get_user(user_id)

    def bump_btc_index(self, user_id: int) -> int:
        """Atomically reserve the next BTC derivation index. Returns the used one."""
        cur = self._conn.execute(
            "SELECT next_btc_index FROM users WHERE id = ?", (user_id,)
        )
        row = cur.fetchone()
        if row is None:
            raise NotFoundError(f"user {user_id} not found")
        used = int(row["next_btc_index"] or 0)
        self._conn.execute(
            "UPDATE users SET next_btc_index = ? WHERE id = ?",
            (used + 1, user_id),
        )
        self._conn.commit()
        return used

    def set_fee_override(self, user_id: int, override: float | None) -> User:
        """Set a fee override (e.g. 0.01 for Friends of the Dev). NULL clears it."""
        if override is not None and not (0.0 <= override < 1.0):
            raise StorageError(f"fee_override out of range: {override}")
        self._conn.execute(
            "UPDATE users SET fee_override = ? WHERE id = ?",
            (override, user_id),
        )
        self._conn.commit()
        return self.get_user(user_id)

    def increment_fee_balance(self, user_id: int, amount_sats: int) -> int:
        """Add to the user's fee balance. Returns the new balance."""
        self._conn.execute(
            "UPDATE users SET fee_balance_sats = fee_balance_sats + ? WHERE id = ?",
            (amount_sats, user_id),
        )
        self._conn.commit()
        row = self._conn.execute(
            "SELECT fee_balance_sats FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"user {user_id} not found")
        return int(row["fee_balance_sats"] or 0)

    def reset_fee_balance(self, user_id: int) -> None:
        self._conn.execute(
            "UPDATE users SET fee_balance_sats = 0 WHERE id = ?", (user_id,)
        )
        self._conn.commit()

    def record_settlement(
        self,
        user_id: int,
        amount_sats: int,
        txid: str,
        address: str | None = None,
    ) -> int:
        """Record a fee payment. Returns settlement id."""
        cur = self._conn.execute(
            """INSERT INTO fee_settlements
               (user_id, amount_sats, txid, address, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (user_id, amount_sats, txid, address, _now()),
        )
        self._conn.commit()
        if cur.lastrowid is None:
            raise StorageError("insert did not return a rowid")
        return int(cur.lastrowid)

    def list_settlements(self, user_id: int) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM fee_settlements WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]
