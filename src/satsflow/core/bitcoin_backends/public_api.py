"""Bitcoin backend using mempool.space's public Esplora-style API.

Watch-only. Can operate in two modes:
  - Real xpub: derives BIP84 addresses from an extended public key.
  - Dev mode: deterministic placeholder addresses for local development.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass

import requests

from satsflow.core.bip32 import Bip32Error, xpub_receive_address
from satsflow.core.bitcoin_backends.base import (
    AddressGenerationError,
    BitcoinBackend,
    BitcoinBackendError,
    PaymentCheckError,
    PaymentResult,
    PaymentStatus,
)

MEMPOOL_API = "https://mempool.space/api"
REQUEST_TIMEOUT = 8.0


@dataclass
class _AddressState:
    """In-memory record of generated addresses."""
    label: str
    address: str
    derivation_index: int
    created_at: float


class PublicAPIBackend(BitcoinBackend):
    """mempool.space-backed watch-only Bitcoin backend."""

    def __init__(
        self,
        session: requests.Session | None = None,
        xpub: str | None = None,
    ) -> None:
        self._session = session or requests.Session()
        self._xpub = xpub
        self._next_index = 0
        self._addresses: dict[str, _AddressState] = {}

    def set_xpub(self, xpub: str | None) -> None:
        """Set or clear the active xpub. Pass None to revert to dev mode."""
        self._xpub = xpub

    def get_new_address(self, label: str) -> str:
        index = self._next_index
        self._next_index += 1

        if self._xpub:
            try:
                address = xpub_receive_address(self._xpub, index)
            except Bip32Error as exc:
                raise AddressGenerationError(f"xpub derivation failed: {exc}") from exc
        else:
            address = self._dev_placeholder(label, index)

        self._addresses[address] = _AddressState(
            label=label,
            address=address,
            derivation_index=index,
            created_at=time.time(),
        )
        return address

    def _dev_placeholder(self, label: str, index: int) -> str:
        seed = f"{label}:{index}".encode()
        digest = hashlib.sha256(seed).hexdigest()
        return "bc1qdev" + digest[:34]

    def check_payment(
        self,
        address: str,
        expected_sats: int,
        min_confirmations: int = 1,
    ) -> PaymentResult:
        try:
            stats = self._fetch_address_stats(address)
        except BitcoinBackendError:
            raise
        except Exception as exc:
            raise PaymentCheckError(str(exc)) from exc

        funded = stats["funded_sats"]
        spent = stats["spent_sats"]
        received = funded - spent

        chain = stats["chain_stats"]
        confirmations = self._estimate_confirmations(chain)

        if received == 0:
            return PaymentResult(
                status=PaymentStatus.NOT_FOUND,
                received_sats=0,
                expected_sats=expected_sats,
                confirmations=0,
                txid=None,
            )

        if received < expected_sats:
            status = PaymentStatus.UNDERPAID
        elif received > expected_sats:
            status = PaymentStatus.OVERPAID
        elif confirmations >= min_confirmations:
            status = PaymentStatus.CONFIRMED
        else:
            status = PaymentStatus.PENDING

        return PaymentResult(
            status=status,
            received_sats=received,
            expected_sats=expected_sats,
            confirmations=confirmations,
            txid=None,
        )

    def get_balance(self, address: str) -> int:
        stats = self._fetch_address_stats(address)
        chain = stats["chain_stats"]
        return chain.get("funded_txo_sum", 0) - chain.get("spent_txo_sum", 0)

    def _fetch_address_stats(self, address: str) -> dict:
        url = f"{MEMPOOL_API}/address/{address}"
        try:
            resp = self._session.get(url, timeout=REQUEST_TIMEOUT)
        except requests.RequestException as exc:
            raise PaymentCheckError(f"request failed: {exc}") from exc

        if resp.status_code != 200:
            raise PaymentCheckError(f"http {resp.status_code} for {address}")

        try:
            data = resp.json()
        except ValueError as exc:
            raise PaymentCheckError("response not valid JSON") from exc

        chain = data.get("chain_stats", {})
        mempool = data.get("mempool_stats", {})

        funded = chain.get("funded_txo_sum", 0) + mempool.get("funded_txo_sum", 0)
        spent = chain.get("spent_txo_sum", 0) + mempool.get("spent_txo_sum", 0)

        return {
            "funded_sats": funded,
            "spent_sats": spent,
            "chain_stats": chain,
            "mempool_stats": mempool,
        }

    @staticmethod
    def _estimate_confirmations(chain_stats: dict) -> int:
        return 1 if chain_stats.get("tx_count", 0) > 0 else 0
