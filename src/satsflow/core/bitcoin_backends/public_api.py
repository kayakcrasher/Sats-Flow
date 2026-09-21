"""Bitcoin backend using mempool.space's public Esplora-style API.

No API key required. Rate limits are generous at SatsFlow's expected scale.

Design:
  - get_new_address() derives from a watch-only xpub using BIP32/BIP44.
    If no xpub is configured, a deterministic mock address is returned
    so the rest of the app can run in dev without real keys.
  - check_payment() queries the address's confirmed + mempool balance
    and compares against expected_sats.
  - No private keys ever touch this module. Watch-only.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass

import requests

from satsflow import config
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
    """In-memory record of what we've generated. Real persistence in Phase 6."""

    label: str
    address: str
    derivation_index: int
    created_at: float


class PublicAPIBackend(BitcoinBackend):
    """mempool.space-backed watch-only Bitcoin backend."""

    def __init__(self, session: requests.Session | None = None) -> None:
        self._session = session or requests.Session()
        self._next_index = 0
        self._addresses: dict[str, _AddressState] = {}

    # --- Address generation -------------------------------------------------

    def get_new_address(self, label: str) -> str:
        """Return a fresh receive address for `label`."""
        index = self._next_index
        self._next_index += 1

        xpub = config.BTC_XPUB
        if xpub:
            address = self._derive_from_xpub(xpub, index)
        else:
            address = self._dev_placeholder(label, index)

        self._addresses[address] = _AddressState(
            label=label,
            address=address,
            derivation_index=index,
            created_at=time.time(),
        )
        return address

    def _derive_from_xpub(self, xpub: str, index: int) -> str:
        """Derive a receive address from an xpub at the given index.

        Full BIP32 derivation is not implemented here yet — this raises
        loudly rather than returning a wrong address. Wire real derivation
        in Phase 8 when self-hosted node support lands.
        """
        raise AddressGenerationError(
            "xpub derivation not yet implemented; "
            "unset BTC_XPUB or complete Phase 8"
        )

    def _dev_placeholder(self, label: str, index: int) -> str:
        """Deterministic fake address for dev, when BTC_XPUB is unset."""
        seed = f"{label}:{index}".encode()
        digest = hashlib.sha256(seed).hexdigest()
        return "bc1qdev" + digest[:34]

    # --- Payment checking ---------------------------------------------------

    def check_payment(
        self,
        address: str,
        expected_sats: int,
        min_confirmations: int = 1,
    ) -> PaymentResult:
        """Query mempool.space for payment status at `address`."""
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
        """Return confirmed balance in sats for `address`."""
        stats = self._fetch_address_stats(address)
        chain = stats["chain_stats"]
        return chain.get("funded_txo_sum", 0) - chain.get("spent_txo_sum", 0)

    # --- HTTP ---------------------------------------------------------------

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
        """Best-effort confirmation count.

        mempool.space doesn't return confirmations per address directly.
        We use tx_count as a proxy — any confirmed tx means at least 1
        confirmation. Real per-tx detail comes in Phase 8 with our node.
        """
        return 1 if chain_stats.get("tx_count", 0) > 0 else 0
