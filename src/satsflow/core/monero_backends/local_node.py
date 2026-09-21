"""Monero backend for a fully self-hosted monerod + monero-wallet-rpc.

Stub for now. Real implementation lands in Phase 8 alongside the Bitcoin
self-hosted backend. Every method raises NodeNotConfigured or
MoneroBackendError so nothing silently does the wrong thing.

When complete, this backend will talk to a locally-running monerod for
chain data and a locally-running monero-wallet-rpc (view-only) for
subaddress generation and payment detection.
"""

from __future__ import annotations

from satsflow import config
from satsflow.core.monero_backends.base import (
    AddressGenerationError,
    MoneroBackend,
    MoneroBackendError,
    PaymentCheckError,
    PaymentResult,
)


class NodeNotConfigured(MoneroBackendError):
    """Raised when the self-hosted backend is used before it's set up."""


class LocalNodeBackend(MoneroBackend):
    """Fully self-hosted monerod + wallet-rpc backend (stub)."""

    def __init__(self) -> None:
        self._node_rpc = config.XMR_NODE_RPC
        self._wallet_rpc = config.XMR_WALLET_RPC

    def _require_config(self) -> None:
        if not (self._node_rpc and self._wallet_rpc):
            raise NodeNotConfigured(
                "XMR_NODE_RPC and XMR_WALLET_RPC must both be set. "
                "Set them in .env, or use SATFLOW_XMR_BACKEND=remote or mock."
            )

    def get_new_address(self, label: str) -> str:
        self._require_config()
        raise AddressGenerationError(
            "self-hosted subaddress generation not yet implemented (Phase 8)"
        )

    def check_payment(
        self,
        address: str,
        expected_piconero: int,
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
