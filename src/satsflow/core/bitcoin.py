"""Public Bitcoin interface for SatsFlow.

Reads config.BTC_BACKEND to decide which backend implementation to use:
  - "public" -> PublicAPIBackend (mempool.space)
  - "node"   -> NodeBackend (self-hosted bitcoind + electrs)

The rest of the app imports from this module and never touches a specific
backend directly. Swapping backends is a config change, not a code change.

Fee model (per-tx forward, no batching):
  Every donation gets two outputs:
      99% -> creator address
       1% -> GNOMEFINANCE address
  Both are on-chain, both visible, both auditable.
"""

from __future__ import annotations

from dataclasses import dataclass

from satsflow import config
from satsflow.core.bitcoin_backends.base import (
    BitcoinBackend,
    BitcoinBackendError,
    PaymentResult,
)


class BitcoinError(Exception):
    """Raised by the public interface when something goes wrong."""


@dataclass(frozen=True)
class FeeSplit:
    """Result of splitting a donation into creator and platform amounts."""

    creator_sats: int
    platform_sats: int
    total_sats: int


def split_fee(amount_sats: int, fee_percent: float | None = None) -> FeeSplit:
    """Split a donation into creator + platform amounts.

    The platform takes a percentage; the creator gets the rest. Rounding
    favors the creator so a creator never loses a satoshi to truncation.
    """
    if amount_sats < 0:
        raise BitcoinError("amount_sats must be non-negative")

    pct = config.FEE_PERCENT if fee_percent is None else fee_percent
    if not (0.0 <= pct < 1.0):
        raise BitcoinError("fee_percent must be in [0, 1)")

    platform = int(amount_sats * pct)
    creator = amount_sats - platform
    return FeeSplit(
        creator_sats=creator,
        platform_sats=platform,
        total_sats=amount_sats,
    )


def _load_backend() -> BitcoinBackend:
    """Instantiate the backend selected by config.BTC_BACKEND."""
    backend_name = config.BTC_BACKEND.lower()

    if backend_name == "public":
        from satsflow.core.bitcoin_backends.public_api import PublicAPIBackend

        return PublicAPIBackend()

    if backend_name == "node":
        from satsflow.core.bitcoin_backends.node import NodeBackend

        return NodeBackend()

    raise BitcoinError(f"unknown BTC_BACKEND: {backend_name!r}")


class Bitcoin:
    """Thin wrapper around the configured backend.

    Usage:
        btc = Bitcoin()
        address = btc.new_address("invoice-123")
        result = btc.check(address, expected_sats=100_000)
    """

    def __init__(
        self,
        backend: BitcoinBackend | None = None,
        xpub: str | None = None,
    ) -> None:
        self._backend = backend or _load_backend()
        if xpub and hasattr(self._backend, "set_xpub"):
            self._backend.set_xpub(xpub)  # type: ignore[attr-defined]

    @property
    def backend(self) -> BitcoinBackend:
        return self._backend

    def new_address(self, label: str) -> str:
        """Generate a fresh receive address for a donation."""
        try:
            return self._backend.get_new_address(label)
        except BitcoinBackendError as exc:
            raise BitcoinError(str(exc)) from exc

    def check(
        self,
        address: str,
        expected_sats: int,
        min_confirmations: int = 1,
    ) -> PaymentResult:
        """Return the payment status for `address`."""
        try:
            return self._backend.check_payment(
                address, expected_sats, min_confirmations
            )
        except BitcoinBackendError as exc:
            raise BitcoinError(str(exc)) from exc

    def balance(self, address: str) -> int:
        """Return confirmed balance in sats for `address`."""
        try:
            return self._backend.get_balance(address)
        except BitcoinBackendError as exc:
            raise BitcoinError(str(exc)) from exc
