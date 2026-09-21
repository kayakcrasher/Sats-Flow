"""Abstract Monero backend interface.

Every Monero backend (remote node, local node, mock) implements this same
interface. The rest of the app talks to `MoneroBackend` and does not care
which implementation is active.

Design:
  - Non-custodial: we only ever need *watch-only* capability. The backend
    never holds spend keys.
  - Monero uses subaddresses for per-invoice receive addresses. A creator's
    wallet has a primary address plus a set of subaddresses. We generate a
    fresh subaddress per donation.
  - Amounts are piconero (1 XMR = 10**12 piconero), integers only.
  - Payment status is structured, not boolean — same pattern as Bitcoin.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable

PICONERO_PER_XMR = 10**12


class MoneroBackendError(Exception):
    """Base for backend failures."""


class AddressGenerationError(MoneroBackendError):
    """Raised when a new subaddress cannot be generated."""


class PaymentCheckError(MoneroBackendError):
    """Raised when payment status cannot be determined."""


class PaymentStatus(str, Enum):
    """Result of a payment check against a watch-only subaddress."""

    PENDING = "pending"          # in mempool / tx pool, 0 confirmations
    CONFIRMED = "confirmed"      # at or above required confirmations
    UNDERPAID = "underpaid"      # some piconero received, less than expected
    OVERPAID = "overpaid"        # more piconero received than expected
    NOT_FOUND = "not_found"      # no transaction seen for this subaddress


@dataclass(frozen=True)
class PaymentResult:
    """Structured result from check_payment()."""

    status: PaymentStatus
    received_piconero: int
    expected_piconero: int
    confirmations: int
    txid: str | None = None

    @property
    def is_final(self) -> bool:
        """True once we should stop polling for this subaddress."""
        return self.status in {
            PaymentStatus.CONFIRMED,
            PaymentStatus.OVERPAID,
        }


@runtime_checkable
class MoneroBackend(Protocol):
    """Watch-only Monero backend.

    Implementations must be safe to call concurrently. They may raise
    MoneroBackendError subclasses on failure.
    """

    def get_new_address(self, label: str) -> str:
        """Generate a fresh subaddress for the given label.

        `label` is opaque to the backend; callers use it to correlate
        subaddresses with invoices.
        """
        ...

    def check_payment(
        self,
        address: str,
        expected_piconero: int,
        min_confirmations: int = 1,
    ) -> PaymentResult:
        """Return payment status for `address` against `expected_piconero`."""
        ...

    def get_balance(self, address: str) -> int:
        """Return current confirmed balance in piconero for `address`."""
        ...
