"""Bitcoin backend for a self-hosted bitcoind + electrs stack.

This is a stub. Real RPC calls land in Phase 8 when the node is running.
For now every method raises NodeNotConfigured so callers get a clear signal
instead of silent wrong behavior.

When complete, this module will:
  - Connect to electrs over its REST or Electrum protocol for address
    history and UTXOs (no bitcoind wallet needed for watch-only).
  - Optionally talk to bitcoind RPC directly for raw chain data.
  - Never hold private keys. Watch-only, same as PublicAPIBackend.
"""

from __future__ import annotations

from satsflow import config
from satsflow.core.bitcoin_backends.base import (
    AddressGenerationError,
    BitcoinBackend,
    PaymentCheckError,
    PaymentResult,
)


class NodeNotConfigured(Exception):
    """Raised when the self-hosted backend is used before it's set up."""


class NodeBackend(BitcoinBackend):
    """Self-hosted bitcoind + electrs backend (stub)."""

    def __init__(self) -> None:
        self._rpc_url = config.BTC_NODE_RPC
        self._electrs_url = config.ELECTRS_URL

    def _require_config(self) -> None:
        if not (self._rpc_url or self._electrs_url):
            raise NodeNotConfigured(
                "BTC_NODE_RPC and ELECTRS_URL are both unset. "
                "Set one in .env, or use SATFLOW_BTC_BACKEND=public."
            )

    def get_new_address(self, label: str) -> str:
        self._require_config()
        raise AddressGenerationError(
            "self-hosted address derivation not yet implemented (Phase 8)"
        )

    def check_payment(
        self,
        address: str,
        expected_sats: int,
        min_confirmations: int = 1,
    ) -> PaymentResult:
        self._require_config()
        raise PaymentCheckError(
            "self-hosted payment checking not yet implemented (Phase 8)"
        )

    def get_balance(self, address: str) -> int:
        self._require_config()
        raise PaymentCheckError(
            "self-hosted balance query not yet implemented (Phase 8)"
        )
