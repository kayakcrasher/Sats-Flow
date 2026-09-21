"""Tests for core.monero and the mock backend. No real network."""
from __future__ import annotations

import pytest

from satsflow.core.monero import (
    MoneroError,
    piconero_to_xmr,
    split_fee,
    xmr_to_piconero,
)
from satsflow.core.monero_backends.base import (
    PICONERO_PER_XMR,
    PaymentCheckError,
    PaymentStatus,
)
from satsflow.core.monero_backends.mock import MockBackend

# ---------------------------------------------------------------------------
# Unit conversions
# ---------------------------------------------------------------------------

class TestConversions:
    def test_piconero_per_xmr_constant(self):
        assert PICONERO_PER_XMR == 10**12

    def test_xmr_to_piconero_whole(self):
        assert xmr_to_piconero(1.0) == 10**12

    def test_xmr_to_piconero_fraction(self):
        assert xmr_to_piconero(0.5) == 500_000_000_000

    def test_xmr_to_piconero_tiny(self):
        assert xmr_to_piconero(0.000000000001) == 1

    def test_xmr_to_piconero_zero(self):
        assert xmr_to_piconero(0.0) == 0

    def test_xmr_to_piconero_negative_rejected(self):
        with pytest.raises(MoneroError, match="non-negative"):
            xmr_to_piconero(-0.1)

    def test_roundtrip_whole(self):
        assert piconero_to_xmr(10**12) == 1.0

    def test_roundtrip_fraction(self):
        assert piconero_to_xmr(500_000_000_000) == 0.5

    def test_roundtrip_zero(self):
        assert piconero_to_xmr(0) == 0.0


# ---------------------------------------------------------------------------
# split_fee
# ---------------------------------------------------------------------------

class TestSplitFee:
    def test_default_1_percent(self):
        s = split_fee(1_000_000_000_000)
        assert s.creator_piconero == 990_000_000_000
        assert s.platform_piconero == 10_000_000_000
        assert s.total_piconero == 1_000_000_000_000

    def test_rounding_favors_creator(self):
        # 1% of 101 = 1.01 -> int() truncates to 1. Creator gets 100.
        s = split_fee(101)
        assert s.creator_piconero == 100
        assert s.platform_piconero == 1

    def test_custom_fee_percent(self):
        s = split_fee(10_000, fee_percent=0.05)
        assert s.creator_piconero == 9_500
        assert s.platform_piconero == 500

    def test_zero_amount(self):
        s = split_fee(0)
        assert s.creator_piconero == 0
        assert s.platform_piconero == 0

    def test_negative_amount_rejected(self):
        with pytest.raises(MoneroError, match="non-negative"):
            split_fee(-1)

    def test_invalid_fee_percent_rejected(self):
        with pytest.raises(MoneroError, match="fee_percent"):
            split_fee(1000, fee_percent=1.0)

    def test_negative_fee_percent_rejected(self):
        with pytest.raises(MoneroError, match="fee_percent"):
            split_fee(1000, fee_percent=-0.1)

    def test_very_small_amount_favors_creator(self):
        # 1% of 1 truncates to 0 platform, 1 creator
        s = split_fee(1)
        assert s.creator_piconero == 1
        assert s.platform_piconero == 0


# ---------------------------------------------------------------------------
# MockBackend
# ---------------------------------------------------------------------------

class TestMockBackendLifecycle:
    def test_get_new_address_returns_string(self):
        m = MockBackend()
        addr = m.get_new_address("invoice-1")
        assert isinstance(addr, str)
        assert len(addr) == 95
        assert addr.startswith("8")  # subaddress prefix

    def test_addresses_are_unique(self):
        m = MockBackend()
        a = m.get_new_address("inv")
        b = m.get_new_address("inv")
        assert a != b

    def test_empty_label_rejected(self):
        m = MockBackend()
        with pytest.raises(Exception, match="non-empty"):
            m.get_new_address("")

    def test_unknown_address_raises_on_check(self):
        m = MockBackend()
        with pytest.raises(PaymentCheckError, match="unknown address"):
            m.check_payment("not-an-address", expected_piconero=1000)

    def test_unknown_address_raises_on_balance(self):
        m = MockBackend()
        with pytest.raises(PaymentCheckError, match="unknown address"):
            m.get_balance("not-an-address")

    def test_reset_clears_state(self):
        m = MockBackend()
        m.get_new_address("inv")
        m.reset()
        assert m._next_index == 0
        assert m._addresses == {}


class TestMockBackendPaymentStatuses:
    def test_not_found_by_default(self):
        m = MockBackend()
        addr = m.get_new_address("inv")
        result = m.check_payment(addr, expected_piconero=1_000_000_000_000)
        assert result.status == PaymentStatus.NOT_FOUND
        assert result.received_piconero == 0
        assert result.confirmations == 0
        assert result.txid is None

    def test_confirmed_exact(self):
        m = MockBackend()
        addr = m.get_new_address("inv")
        m.set_received(addr, piconero=1_000_000_000_000, confirmations=3, txid="abc")
        result = m.check_payment(addr, expected_piconero=1_000_000_000_000)
        assert result.status == PaymentStatus.CONFIRMED
        assert result.received_piconero == 1_000_000_000_000
        assert result.confirmations == 3
        assert result.txid == "abc"
        assert result.is_final is True

    def test_pending_zero_conf(self):
        m = MockBackend()
        addr = m.get_new_address("inv")
        m.set_received(addr, piconero=1_000_000_000_000, confirmations=0)
        result = m.check_payment(addr, expected_piconero=1_000_000_000_000)
        assert result.status == PaymentStatus.PENDING
        assert result.confirmations == 0
        assert result.is_final is False

    def test_pending_below_min_conf(self):
        m = MockBackend()
        addr = m.get_new_address("inv")
        m.set_received(addr, piconero=1_000_000_000_000, confirmations=1)
        result = m.check_payment(
            addr, expected_piconero=1_000_000_000_000, min_confirmations=5
        )
        assert result.status == PaymentStatus.PENDING

    def test_underpaid(self):
        m = MockBackend()
        addr = m.get_new_address("inv")
        m.set_received(addr, piconero=500_000_000_000, confirmations=2)
        result = m.check_payment(addr, expected_piconero=1_000_000_000_000)
        assert result.status == PaymentStatus.UNDERPAID
        assert result.is_final is False

    def test_overpaid(self):
        m = MockBackend()
        addr = m.get_new_address("inv")
        m.set_received(addr, piconero=2_000_000_000_000, confirmations=2)
        result = m.check_payment(addr, expected_piconero=1_000_000_000_000)
        assert result.status == PaymentStatus.OVERPAID
        assert result.is_final is True


class TestMockBackendBalance:
    def test_balance_confirmed(self):
        m = MockBackend()
        addr = m.get_new_address("inv")
        m.set_received(addr, piconero=1_000_000_000_000, confirmations=3)
        assert m.get_balance(addr) == 1_000_000_000_000

    def test_balance_unconfirmed_is_zero(self):
        m = MockBackend()
        addr = m.get_new_address("inv")
        m.set_received(addr, piconero=1_000_000_000_000, confirmations=0)
        assert m.get_balance(addr) == 0

    def test_balance_zero_when_nothing_received(self):
        m = MockBackend()
        addr = m.get_new_address("inv")
        assert m.get_balance(addr) == 0
