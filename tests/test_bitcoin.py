"""Tests for core.bitcoin and the public API backend. No real network."""
from __future__ import annotations

from unittest.mock import Mock

import pytest
import requests

from satsflow.core.bitcoin import BitcoinError, split_fee
from satsflow.core.bitcoin_backends.base import (
    PaymentCheckError,
    PaymentStatus,
)
from satsflow.core.bitcoin_backends.public_api import PublicAPIBackend

# ---------------------------------------------------------------------------
# split_fee
# ---------------------------------------------------------------------------

class TestSplitFee:
    def test_default_1_percent(self):
        s = split_fee(100_000)
        assert s.creator_sats == 99_000
        assert s.platform_sats == 1_000
        assert s.total_sats == 100_000

    def test_rounding_favors_creator(self):
        # 1% of 101 = 1.01 -> int() truncates to 1. Creator gets 100.
        s = split_fee(101)
        assert s.creator_sats == 100
        assert s.platform_sats == 1

    def test_custom_fee_percent(self):
        s = split_fee(10_000, fee_percent=0.05)
        assert s.creator_sats == 9_500
        assert s.platform_sats == 500

    def test_zero_amount(self):
        s = split_fee(0)
        assert s.creator_sats == 0
        assert s.platform_sats == 0

    def test_negative_amount_rejected(self):
        with pytest.raises(BitcoinError, match="non-negative"):
            split_fee(-1)

    def test_invalid_fee_percent_rejected(self):
        with pytest.raises(BitcoinError, match="fee_percent"):
            split_fee(1000, fee_percent=1.0)

    def test_negative_fee_percent_rejected(self):
        with pytest.raises(BitcoinError, match="fee_percent"):
            split_fee(1000, fee_percent=-0.1)


# ---------------------------------------------------------------------------
# PublicAPIBackend — helpers
# ---------------------------------------------------------------------------

def mempool_ok(funded: int = 0, spent: int = 0, tx_count: int = 0) -> Mock:
    r = Mock()
    r.status_code = 200
    r.json.return_value = {
        "address": "bc1qdevtest",
        "chain_stats": {
            "funded_txo_sum": funded,
            "spent_txo_sum": spent,
            "tx_count": tx_count,
        },
        "mempool_stats": {
            "funded_txo_sum": 0,
            "spent_txo_sum": 0,
            "tx_count": 0,
        },
    }
    return r


def mempool_mempool_only(funded: int = 0, tx_count: int = 0) -> Mock:
    """Response where funds are only in mempool (0 confs)."""
    r = Mock()
    r.status_code = 200
    r.json.return_value = {
        "address": "bc1qdevtest",
        "chain_stats": {
            "funded_txo_sum": 0,
            "spent_txo_sum": 0,
            "tx_count": 0,
        },
        "mempool_stats": {
            "funded_txo_sum": funded,
            "spent_txo_sum": 0,
            "tx_count": tx_count,
        },
    }
    return r


def http_error(status: int = 500) -> Mock:
    r = Mock()
    r.status_code = status
    return r


class FakeSession:
    def __init__(self):
        self.calls: list[dict] = []
        self.responses: list = []

    def queue(self, *items) -> None:
        self.responses.extend(items)

    def get(self, url, timeout=None):
        self.calls.append({"url": url, "timeout": timeout})
        if not self.responses:
            raise AssertionError("FakeSession.get called but no response queued")
        nxt = self.responses.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt


@pytest.fixture
def fake_session():
    return FakeSession()


@pytest.fixture
def backend(fake_session, monkeypatch):
    # Ensure no xpub is configured so dev placeholder path is used
    monkeypatch.setattr("satsflow.config.BTC_XPUB", "", raising=False)
    return PublicAPIBackend(session=fake_session)


# ---------------------------------------------------------------------------
# Address generation
# ---------------------------------------------------------------------------

class TestAddressGeneration:
    def test_returns_address(self, backend):
        addr = backend.get_new_address("invoice-1")
        assert isinstance(addr, str)
        assert addr.startswith("bc1qdev")

    def test_deterministic_for_same_label_and_index(self, backend):
        a = backend.get_new_address("invoice-1")
        b = backend.get_new_address("invoice-1")
        # Different indices -> different addresses
        assert a != b

    def test_index_increments(self, backend):
        a = backend.get_new_address("inv")
        b = backend.get_new_address("inv")
        assert a != b
        assert backend._next_index == 2

    def test_xpub_derives_real_address(self, fake_session):
        # BIP84 test vector — same xpub used in tests/test_bip32.py
        xpub = (
            "zpub6rFR7y4Q2AijBEqTUquhVz398htDFrtymD9xYYfG1m4wAcvPhXNfE3EfH1r1ADqtfSdVC"
            "ToUG868RvUUkgDKf31mGDtKsAYz2oz2AGutZYs"
        )
        b = PublicAPIBackend(session=fake_session, xpub=xpub)
        addr0 = b.get_new_address("inv")
        addr1 = b.get_new_address("inv")
        assert addr0 == "bc1qcr8te4kr609gcawutmrza0j4xv80jy8z306fyu"
        assert addr1 == "bc1qnjg0jd8228aq7egyzacy8cys3knf9xvrerkf9g"

    def test_invalid_xpub_raises(self, fake_session):
        b = PublicAPIBackend(session=fake_session, xpub="not-a-real-xpub")
        with pytest.raises(Exception, match="xpub derivation failed"):
            b.get_new_address("inv")


# ---------------------------------------------------------------------------
# check_payment statuses
# ---------------------------------------------------------------------------

class TestCheckPayment:
    def test_not_found(self, backend, fake_session):
        fake_session.queue(mempool_ok(funded=0, spent=0, tx_count=0))
        result = backend.check_payment("bc1qtest", expected_sats=100_000)
        assert result.status == PaymentStatus.NOT_FOUND
        assert result.received_sats == 0
        assert result.confirmations == 0

    def test_confirmed_exact(self, backend, fake_session):
        fake_session.queue(mempool_ok(funded=100_000, spent=0, tx_count=1))
        result = backend.check_payment("bc1qtest", expected_sats=100_000)
        assert result.status == PaymentStatus.CONFIRMED
        assert result.received_sats == 100_000

    def test_overpaid(self, backend, fake_session):
        fake_session.queue(mempool_ok(funded=150_000, spent=0, tx_count=1))
        result = backend.check_payment("bc1qtest", expected_sats=100_000)
        assert result.status == PaymentStatus.OVERPAID
        assert result.is_final is True

    def test_underpaid(self, backend, fake_session):
        fake_session.queue(mempool_ok(funded=50_000, spent=0, tx_count=1))
        result = backend.check_payment("bc1qtest", expected_sats=100_000)
        assert result.status == PaymentStatus.UNDERPAID
        assert result.is_final is False

    def test_pending_zero_conf(self, backend, fake_session):
        fake_session.queue(mempool_mempool_only(funded=100_000, tx_count=1))
        result = backend.check_payment("bc1qtest", expected_sats=100_000)
        assert result.status == PaymentStatus.PENDING
        assert result.confirmations == 0
        assert result.is_final is False

    def test_http_error(self, backend, fake_session):
        fake_session.queue(http_error(500))
        with pytest.raises(PaymentCheckError, match="http 500"):
            backend.check_payment("bc1qtest", expected_sats=100_000)

    def test_network_error(self, backend, fake_session):
        fake_session.queue(requests.ConnectionError("dns fail"))
        with pytest.raises(PaymentCheckError, match="request failed"):
            backend.check_payment("bc1qtest", expected_sats=100_000)

    def test_bad_json(self, backend, fake_session):
        r = Mock(status_code=200)
        r.json.side_effect = ValueError("nope")
        fake_session.queue(r)
        with pytest.raises(PaymentCheckError, match="not valid JSON"):
            backend.check_payment("bc1qtest", expected_sats=100_000)


# ---------------------------------------------------------------------------
# Balance
# ---------------------------------------------------------------------------

class TestBalance:
    def test_balance_confirmed(self, backend, fake_session):
        fake_session.queue(mempool_ok(funded=200_000, spent=50_000, tx_count=2))
        assert backend.get_balance("bc1qtest") == 150_000

    def test_balance_zero(self, backend, fake_session):
        fake_session.queue(mempool_ok(funded=0, spent=0, tx_count=0))
        assert backend.get_balance("bc1qtest") == 0
