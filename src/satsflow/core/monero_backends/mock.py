"""In-memory Monero backend for tests and local dev.

No network calls. No real wallet. You can programmatically set what a
subaddress "received" so tests can drive every status branch deterministically.

Usage:
    m = MockBackend()
    addr = m.get_new_address("invoice-1")
    m.set_received(addr, piconero=1_000_000_000_000, confirmations=3)
    result = m.check_payment(addr, expected_piconero=1_000_000_000_000)
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field

from satsflow.core.monero_backends.base import (
    AddressGenerationError,
    MoneroBackend,
    PaymentCheckError,
    PaymentResult,
    PaymentStatus,
)


@dataclass
class _MockAddress:
    label: str
    address: str
    index: int
    created_at: float
    received_piconero: int = 0
    confirmations: int = 0
    txid: str | None = None


@dataclass
class MockBackend(MoneroBackend):
    """In-memory backend. Programmable for tests."""

    _next_index: int = 0
    _addresses: dict[str, _MockAddress] = field(default_factory=dict)

    # --- Test/dev control ---------------------------------------------------

    def set_received(
        self,
        address: str,
        piconero: int,
        confirmations: int = 0,
        txid: str | None = None,
    ) -> None:
        """Simulate a payment landing at `address`."""
        entry = self._addresses.get(address)
        if entry is None:
            raise PaymentCheckError(f"unknown address: {address}")
        entry.received_piconero = piconero
        entry.confirmations = confirmations
        entry.txid = txid

    def reset(self) -> None:
        """Clear all state. Useful between tests."""
        self._next_index = 0
        self._addresses.clear()

    # --- MoneroBackend interface -------------------------------------------

    def get_new_address(self, label: str) -> str:
        """Return a deterministic fake subaddress for `label`."""
        if not label:
            raise AddressGenerationError("label must be non-empty")

        index = self._next_index
        self._next_index += 1

        seed = f"mock-xmr:{label}:{index}".encode()
        digest = hashlib.sha256(seed).hexdigest()
        # Monero addresses are 95 chars starting with '4' (primary) or '8' (sub)
        address = "8" + (digest + digest)[:94]

        self._addresses[address] = _MockAddress(
            label=label,
            address=address,
            index=index,
            created_at=time.time(),
        )
        return address

    def check_payment(
        self,
        address: str,
        expected_piconero: int,
        min_confirmations: int = 1,
    ) -> PaymentResult:
        entry = self._addresses.get(address)
        if entry is None:
            raise PaymentCheckError(f"unknown address: {address}")

        received = entry.received_piconero
        confs = entry.confirmations

        if received == 0:
            status = PaymentStatus.NOT_FOUND
        elif received < expected_piconero:
            status = PaymentStatus.UNDERPAID
        elif received > expected_piconero:
            status = PaymentStatus.OVERPAID
        elif confs >= min_confirmations:
            status = PaymentStatus.CONFIRMED
        else:
            status = PaymentStatus.PENDING

        return PaymentResult(
            status=status,
            received_piconero=received,
            expected_piconero=expected_piconero,
            confirmations=confs,
            txid=entry.txid,
        )

    def get_balance(self, address: str) -> int:
        entry = self._addresses.get(address)
        if entry is None:
            raise PaymentCheckError(f"unknown address: {address}")
        # Only confirmed balance counts
        if entry.confirmations >= 1:
            return entry.received_piconero
        return 0
