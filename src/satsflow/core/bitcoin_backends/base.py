"""Abstract Bitcoin backend interface.

Every Bitcoin backend (public API, self-hosted node, mock) implements this
same interface. The rest of the app talks to `BitcoinBackend` and does not
care which implementation is active.

Design:
  - Non-custodial: we only ever need *watch-only* capability. The backend
    never holds spend keys, never signs transactions.
  - Address generation is per-invoice. A creator's xpub derives a fresh
    receive address for each donation. This gives us reconciliation for
    free and avoids address reuse.
  - Payment checking returns a structured status, not a boolean, so the
    caller can react differently to "pending", "confirmed", "underpaid".
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable


class BitcoinBackendError(Exception):
    """Base for backend failures."""


class AddressGenerationError(BitcoinBackendError):
    """Raised when a new address cannot be derived."""


class PaymentCheckError(BitcoinBackendError):
    """Raised when payment status cannot be determined."""


class PaymentStatus(str, Enum):
    """Result of a payment check against a watch-only address."""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    UNDERPAID = "underpaid"
    OVERPAID = "overpaid"
    NOT_FOUND = "not_found"


@dataclass(frozen=True)
class PaymentResult:
    """Structured result from check_payment()."""

    status: PaymentStatus
    received_sats: int
    expected_sats: int
    confirmations: int
    txid: str | None = None

    @property
    def is_final(self) -> bool:
        """True once we should stop polling for this address."""
        return self.status in {
            PaymentStatus.CONFIRMED,
            PaymentStatus.OVERPAID,
        }


@runtime_checkable
class BitcoinBackend(Protocol):
    """Watch-only Bitcoin backend."""

    def get_new_address(self, label: str) -> str:
        """Derive a fresh receive address for the given label."""
        ...

    def check_payment(
        self,
        address: str,
        expected_sats: int,
        min_confirmations: int = 1,
    ) -> PaymentResult:
        """Return payment status for `address` against `expected_sats`."""
        ...

    def get_balance(self, address: str) -> int:
        """Return current confirmed balance in sats for `address`."""
        ...
