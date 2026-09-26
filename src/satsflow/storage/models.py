"""Data models for SatsFlow storage."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Creator:
    id: int | None
    slug: str
    display_name: str
    bio: str
    btc_address: str | None
    xmr_address: str | None
    btc_xpub: str | None
    next_btc_index: int
    fee_override: float | None
    password_hash: str | None
    created_at: int


@dataclass(frozen=True)
class Donation:
    id: int | None
    creator_id: int
    coin: str                     # "BTC" or "XMR"
    amount: int                   # sats for BTC, piconero for XMR
    usd_at_receipt: float | None
    txid: str | None
    address: str | None
    donor_name: str | None
    message: str | None
    created_at: int
    confirmed_at: int | None
    pinned: bool = False
    read_at: int | None = None


@dataclass(frozen=True)
class Claim:
    id: int | None
    donation_id: int
    token: str
    claimed_at: int
