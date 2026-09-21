"""Public Monero interface for SatsFlow.

Reads config.XMR_BACKEND to decide which backend implementation to use:
  - "remote" -> RemoteNodeBackend (remote monerod + local wallet-rpc)
  - "local"  -> LocalNodeBackend  (self-hosted monerod + wallet-rpc)
  - "mock"   -> MockBackend        (dev / tests, no network)

The rest of the app imports from this module and never touches a specific
backend directly. Swapping backends is a config change, not a code change.

Fee model (per-tx forward, no batching):
  Every donation splits on-chain:
      99% -> creator subaddress
       1% -> GNOMEFINANCE address
  Amounts are piconero (1 XMR = 10**12 piconero), integers only.
"""

from __future__ import annotations

from dataclasses import dataclass

from satsflow import config
from satsflow.core.monero_backends.base import (
    PICONERO_PER_XMR,
    MoneroBackend,
    MoneroBackendError,
    PaymentResult,
)


class MoneroError(Exception):
    """Raised by the public interface when something goes wrong."""


@dataclass(frozen=True)
class FeeSplit:
    """Result of splitting a donation into creator and platform amounts."""

    creator_piconero: int
    platform_piconero: int
    total_piconero: int


def split_fee(amount_piconero: int, fee_percent: float | None = None) -> FeeSplit:
    """Split a donation into creator + platform amounts.

    The platform takes a percentage; the creator gets the rest. Rounding
    favors the creator so a creator never loses a piconero to truncation.
    """
    if amount_piconero < 0:
        raise MoneroError("amount_piconero must be non-negative")

    pct = config.FEE_PERCENT if fee_percent is None else fee_percent
    if not (0.0 <= pct < 1.0):
        raise MoneroError("fee_percent must be in [0, 1)")

    platform = int(amount_piconero * pct)
    creator = amount_piconero - platform
    return FeeSplit(
        creator_piconero=creator,
        platform_piconero=platform,
        total_piconero=amount_piconero,
    )


def xmr_to_piconero(xmr: float) -> int:
    """Convert XMR (float) to piconero (int)."""
    if xmr < 0:
        raise MoneroError("xmr amount must be non-negative")
    return round(xmr * PICONERO_PER_XMR)


def piconero_to_xmr(piconero: int) -> float:
    """Convert piconero (int) to XMR (float)."""
    return piconero / PICONERO_PER_XMR


def _load_backend() -> MoneroBackend:
    """Instantiate the backend selected by config.XMR_BACKEND."""
    backend_name = config.XMR_BACKEND.lower()

    if backend_name == "remote":
        from satsflow.core.monero_backends.remote_node import RemoteNodeBackend

        return RemoteNodeBackend()

    if backend_name == "local":
        from satsflow.core.monero_backends.local_node import LocalNodeBackend

        return LocalNodeBackend()

    if backend_name == "mock":
        from satsflow.core.monero_backends.mock import MockBackend

        return MockBackend()

    raise MoneroError(f"unknown XMR_BACKEND: {backend_name!r}")


class Monero:
    """Thin wrapper around the configured backend.

    Usage:
        xmr = Monero()
        address = xmr.new_address("invoice-123")
        result = xmr.check(address, expected_piconero=1_000_000_000_000)
    """

    def __init__(self, backend: MoneroBackend | None = None) -> None:
        self._backend = backend or _load_backend()

    @property
    def backend(self) -> MoneroBackend:
        return self._backend

    def new_address(self, label: str) -> str:
        """Generate a fresh subaddress for a donation."""
        try:
            return self._backend.get_new_address(label)
        except MoneroBackendError as exc:
            raise MoneroError(str(exc)) from exc

    def check(
        self,
        address: str,
        expected_piconero: int,
        min_confirmations: int = 1,
    ) -> PaymentResult:
        """Return the payment status for `address`."""
        try:
            return self._backend.check_payment(
                address, expected_piconero, min_confirmations
            )
        except MoneroBackendError as exc:
            raise MoneroError(str(exc)) from exc

    def balance(self, address: str) -> int:
        """Return confirmed balance in piconero for `address`."""
        try:
            return self._backend.get_balance(address)
        except MoneroBackendError as exc:
            raise MoneroError(str(exc)) from exc
