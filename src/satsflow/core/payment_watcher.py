"""Poll pending donations and update their status in the database.

Called by the invoice page every few seconds. Also usable from a
background scheduler if we add one later.

Design:
  - Only checks donations that are not yet confirmed.
  - Normalizes Bitcoin (sats) and Monero (piconero) results behind
    one interface so callers don't care which coin is being watched.
  - On final status (CONFIRMED or OVERPAID), writes txid + confirmed_at
    to the database. Idempotent — safe to call repeatedly.
"""

from __future__ import annotations

from dataclasses import dataclass

from satsflow.core.bitcoin import Bitcoin, BitcoinError
from satsflow.core.bitcoin_backends.base import (
    PaymentResult as BtcPaymentResult,
)
from satsflow.core.monero import Monero, MoneroError
from satsflow.core.monero_backends.base import (
    PaymentResult as XmrPaymentResult,
)
from satsflow.storage.db import Database
from satsflow.storage.models import Donation


class WatchError(Exception):
    """Raised when a donation cannot be checked."""


@dataclass(frozen=True)
class WatchResult:
    """Normalized result for the invoice page."""

    donation_id: int
    coin: str
    status: str
    received: int
    expected: int
    confirmations: int
    txid: str | None
    is_final: bool


class PaymentWatcher:
    """Checks pending donations and updates them on payment."""

    def __init__(self, db: Database) -> None:
        self._db = db
        self._btc: Bitcoin | None = None
        self._xmr: Monero | None = None

    def _backend_for(self, coin: str) -> Bitcoin | Monero:
        if coin == "BTC":
            if self._btc is None:
                self._btc = Bitcoin()
            return self._btc
        if coin == "XMR":
            if self._xmr is None:
                self._xmr = Monero()
            return self._xmr
        raise WatchError(f"unsupported coin: {coin}")

    def check(self, donation_id: int, min_confirmations: int = 1) -> WatchResult:
        try:
            donation = self._db.get_donation(donation_id)
        except Exception as exc:
            raise WatchError(str(exc)) from exc

        # Already confirmed — return without re-querying the network.
        if donation.confirmed_at is not None:
            return WatchResult(
                donation_id=donation_id,
                coin=donation.coin,
                status="confirmed",
                received=donation.amount,
                expected=donation.amount,
                confirmations=999,
                txid=donation.txid,
                is_final=True,
            )

        if not donation.address:
            raise WatchError(f"donation {donation_id} has no address")

        # Dev placeholder addresses are not valid Bitcoin addresses.
        # mempool.space returns 400 for them. Skip the network call.
        if donation.address.startswith("bc1qdev"):
            return WatchResult(
                donation_id=donation_id,
                coin=donation.coin,
                status="not_found",
                received=0,
                expected=donation.amount,
                confirmations=0,
                txid=None,
                is_final=False,
            )

        backend = self._backend_for(donation.coin)

        try:
            raw = backend.check(donation.address, donation.amount, min_confirmations)
        except (BitcoinError, MoneroError) as exc:
            raise WatchError(str(exc)) from exc

        normalized = self._normalize(raw, donation)

        if normalized.is_final:
            confirmed = self._db.confirm_donation(donation_id, txid=normalized.txid)
            # Only credit the fee balance once — check if this donation
            # was already confirmed before this call.
            if donation.confirmed_at is None and confirmed.platform_fee_sats > 0:
                self._db.increment_fee_balance(
                    confirmed.creator_id, confirmed.platform_fee_sats
                )

        return normalized

    @staticmethod
    def _normalize(raw: BtcPaymentResult | XmrPaymentResult, donation: Donation) -> WatchResult:
        if donation.coin == "BTC":
            received = raw.received_sats  # type: ignore[union-attr]
        else:
            received = raw.received_piconero  # type: ignore[union-attr]

        return WatchResult(
            donation_id=donation.id or 0,
            coin=donation.coin,
            status=raw.status.value,
            received=received,
            expected=donation.amount,
            confirmations=raw.confirmations,
            txid=raw.txid,
            is_final=raw.is_final,
        )
