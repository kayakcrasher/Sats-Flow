"""Monero backend using monero-wallet-rpc.

Points at a local `monero-wallet-rpc` process. That wallet can itself be
connected to a remote `monerod` node — this is the standard hybrid setup:

    [ remote monerod ]  <- blockchain data
            |
    [ local wallet-rpc ]  <- holds view key, no spend key needed
            |
    [ SatsFlow backend ]

Security:
  - Wallet is opened in *view-only* mode. The spend key never touches this
    process.
  - RPC is assumed to be on localhost. If you bind it to a network address,
    put it behind TLS + auth. This module does not add auth on top.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import requests

from satsflow import config
from satsflow.core.monero_backends.base import (
    AddressGenerationError,
    MoneroBackend,
    MoneroBackendError,
    PaymentCheckError,
    PaymentResult,
    PaymentStatus,
)

REQUEST_TIMEOUT = 10.0


@dataclass
class _Subaddress:
    label: str
    address: str
    index: int
    created_at: float


class RemoteNodeBackend(MoneroBackend):
    """Backend that talks to a local monero-wallet-rpc over JSON-RPC."""

    def __init__(self, rpc_url: str | None = None) -> None:
        url = rpc_url or config.XMR_WALLET_RPC
        if not url:
            raise MoneroBackendError(
                "XMR_WALLET_RPC is unset. Set it in .env, "
                "or use SATFLOW_XMR_BACKEND=mock for dev."
            )
        self._url = url
        self._session = requests.Session()
        self._next_index = 1  # subaddress index 0 is the primary address
        self._subaddresses: dict[str, _Subaddress] = {}

    # --- Address generation -------------------------------------------------

    def get_new_address(self, label: str) -> str:
        """Create a fresh subaddress via monero-wallet-rpc."""
        index = self._next_index
        self._next_index += 1

        try:
            result = self._rpc("create_address", {"account_index": 0, "label": label})
        except MoneroBackendError as exc:
            raise AddressGenerationError(str(exc)) from exc

        address = result.get("address")
        if not isinstance(address, str) or not address:
            raise AddressGenerationError("wallet-rpc returned no address")

        # wallet-rpc assigns its own index; trust it over our counter.
        actual_index = result.get("address_index", index)

        self._subaddresses[address] = _Subaddress(
            label=label,
            address=address,
            index=actual_index,
            created_at=time.time(),
        )
        return address

    # --- Payment checking ---------------------------------------------------

    def check_payment(
        self,
        address: str,
        expected_piconero: int,
        min_confirmations: int = 1,
    ) -> PaymentResult:
        entry = self._subaddresses.get(address)
        if entry is None:
            # Unknown to us, but maybe the wallet knows it. Fall back to a
            # balance lookup by index — but we don't know the index. Refuse.
            raise PaymentCheckError(
                f"address not tracked by this backend: {address}"
            )

        try:
            result = self._rpc(
                "get_payments",
                {"payment_id": "", "account_index": 0},
            )
        except MoneroBackendError as exc:
            raise PaymentCheckError(str(exc)) from exc

        payments = result.get("payments", []) or []
        received = 0
        confirmations = 0
        txid = None

        for p in payments:
            if p.get("address") != address:
                continue
            received += int(p.get("amount", 0))
            # monero-wallet-rpc reports confirmations in `get_bulk_payments`
            # but `get_payments` returns height; approximate here.
            confirmations = max(confirmations, int(p.get("confirmations", 0)))
            txid = p.get("tx_hash") or txid

        if received == 0:
            status = PaymentStatus.NOT_FOUND
        elif received < expected_piconero:
            status = PaymentStatus.UNDERPAID
        elif received > expected_piconero:
            status = PaymentStatus.OVERPAID
        elif confirmations >= min_confirmations:
            status = PaymentStatus.CONFIRMED
        else:
            status = PaymentStatus.PENDING

        return PaymentResult(
            status=status,
            received_piconero=received,
            expected_piconero=expected_piconero,
            confirmations=confirmations,
            txid=txid,
        )

    def get_balance(self, address: str) -> int:
        entry = self._subaddresses.get(address)
        if entry is None:
            raise PaymentCheckError(f"address not tracked: {address}")

        try:
            result = self._rpc(
                "get_balance",
                {"account_index": 0, "address_indices": [entry.index]},
            )
        except MoneroBackendError as exc:
            raise PaymentCheckError(str(exc)) from exc

        # wallet-rpc returns per-subaddress balances
        per = result.get("per_subaddress", []) or []
        for row in per:
            if row.get("address") == address:
                return int(row.get("balance", 0))
        return 0

    # --- JSON-RPC -----------------------------------------------------------

    def _rpc(self, method: str, params: dict) -> dict:
        payload: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": "0",
            "method": method,
            "params": params,
        }
        try:
            resp = self._session.post(self._url, json=payload, timeout=REQUEST_TIMEOUT)
        except requests.RequestException as exc:
            raise MoneroBackendError(f"rpc request failed: {exc}") from exc

        if resp.status_code != 200:
            raise MoneroBackendError(f"rpc http {resp.status_code}")

        try:
            data = resp.json()
        except ValueError as exc:
            raise MoneroBackendError("rpc response not valid JSON") from exc

        if "error" in data:
            raise MoneroBackendError(f"rpc error: {data['error']}")

        result = data.get("result")
        if not isinstance(result, dict):
            raise MoneroBackendError("rpc response missing result")
        return result
