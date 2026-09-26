"""Tests for core.fees tier logic."""
from __future__ import annotations

import pytest

from satsflow.core.fees import (
    FEE_TIERS,
    days_until_next_tier,
    fee_percent_for,
    tier_name,
)

DAY = 86400
BASE = 1_700_000_000


class TestFeeTiers:
    def test_day_0_is_launch(self):
        assert fee_percent_for(BASE, now=BASE) == 0.035

    def test_day_13_is_launch(self):
        assert fee_percent_for(BASE, now=BASE + 13 * DAY) == 0.035

    def test_day_14_is_growth(self):
        assert fee_percent_for(BASE, now=BASE + 14 * DAY) == 0.025

    def test_day_59_is_growth(self):
        assert fee_percent_for(BASE, now=BASE + 59 * DAY) == 0.025

    def test_day_60_is_permanent(self):
        assert fee_percent_for(BASE, now=BASE + 60 * DAY) == 0.020

    def test_day_365_is_permanent(self):
        assert fee_percent_for(BASE, now=BASE + 365 * DAY) == 0.020

    def test_override_wins(self):
        assert fee_percent_for(BASE, override=0.01, now=BASE + 365 * DAY) == 0.01

    def test_override_zero(self):
        assert fee_percent_for(BASE, override=0.0, now=BASE) == 0.0

    def test_override_out_of_range(self):
        with pytest.raises(ValueError):
            fee_percent_for(BASE, override=1.5, now=BASE)

    def test_negative_age_is_launch(self):
        assert fee_percent_for(BASE, now=BASE - 100 * DAY) == 0.035


class TestDaysUntilNextTier:
    def test_day_0_returns_14(self):
        assert days_until_next_tier(BASE, now=BASE) == 14

    def test_day_10_returns_4(self):
        assert days_until_next_tier(BASE, now=BASE + 10 * DAY) == 4

    def test_day_14_returns_46(self):
        assert days_until_next_tier(BASE, now=BASE + 14 * DAY) == 46

    def test_day_60_returns_none(self):
        assert days_until_next_tier(BASE, now=BASE + 60 * DAY) is None

    def test_override_returns_none(self):
        assert days_until_next_tier(BASE, override=0.01, now=BASE) is None


class TestTierName:
    def test_launch(self):
        assert tier_name(BASE, now=BASE) == "Launch"

    def test_growth(self):
        assert tier_name(BASE, now=BASE + 20 * DAY) == "Growth"

    def test_permanent(self):
        assert tier_name(BASE, now=BASE + 100 * DAY) == "Permanent"

    def test_friends_override(self):
        assert tier_name(BASE, override=0.01, now=BASE) == "Friends of the Dev"

    def test_cofounder_override(self):
        assert tier_name(BASE, override=0.0, now=BASE) == "Cofounder"


def test_tiers_ordered():
    thresholds = [t for t, _ in FEE_TIERS]
    assert thresholds[-1] is None
    non_none = [t for t in thresholds if t is not None]
    assert non_none == sorted(non_none)
