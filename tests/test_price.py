"""Tests for core.price.PriceFeed.

No real network calls. A FakeSession stubs requests.Session.get() and
returns canned Kraken-shaped responses. A FakeClock lets us control time
so cache TTL behavior is deterministic.
"""

from __future__ import annotations

import json
from unittest.mock import Mock

import pytest
import requests

from satsflow.core import price as price_mod
from satsflow.core.price import PriceFeed, PriceFeedError


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------

class FakeClock:
    def __init__(self, start: float = 1_000_000.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def kraken_ok(price: str = "50000.0") -> Mock:
    """A fake 200 response with a valid Kraken ticker body."""
    r = Mock()
    r.status_code = 200
    r.json.return_value = {
        "error": [],
        "result": {
            "XXBTZUSD": {
                "c": [price, "0.001"],
                "h": ["51000.0", "52000.0"],
                "l": ["49000.0", "48000.0"],
            }
        },
    }
    return r


def kraken_err(message: str = "EQuery:Unknown asset pair") -> Mock:
    r = Mock()
    r.status_code = 200
    r.json.return_value = {"error": [message], "result": {}}
    return r


def http_error(status: int = 500) -> Mock:
    r = Mock()
    r.status_code = status
    return r


class FakeSession:
    """Minimal requests.Session replacement with scripted responses."""

    def __init__(self):
        self.calls: list[dict] = []
        self.responses: list[Mock | Exception] = []

    def queue(self, *items: Mock | Exception) -> None:
        self.responses.extend(items)

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": params, "timeout": timeout})
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
def fake_clock():
    return FakeClock()


@pytest.fixture
def feed(fake_session, fake_clock):
    return PriceFeed(cache_ttl=60.0, max_stale=300.0, session=fake_session, clock=fake_clock)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestBasicFetch:
    def test_fetch_btc(self, feed, fake_session):
        fake_session.queue(kraken_ok("50000.0"))
        assert feed.usd("BTC") == 50000.0

    def test_fetch_xmr(self, feed, fake_session):
        fake_session.queue(kraken_ok("150.25"))
        assert feed.usd("XMR") == 150.25

    def test_coin_is_case_insensitive(self, feed, fake_session):
        fake_session.queue(kraken_ok("50000.0"))
        assert feed.usd("btc") == 50000.0

    def test_uses_correct_pair_names(self, feed, fake_session):
        fake_session.queue(kraken_ok(), kraken_ok())
        feed.usd("BTC")
        feed.usd("XMR")
        assert fake_session.calls[0]["params"]["pair"] == "XXBTZUSD"
        assert fake_session.calls[1]["params"]["pair"] == "XXMRZUSD"

    def test_unsupported_coin_raises(self, feed):
        with pytest.raises(PriceFeedError, match="unsupported coin"):
            feed.usd("DOGE")


# ---------------------------------------------------------------------------
# Cache behavior
# ---------------------------------------------------------------------------

class TestCache:
    def test_second_call_hits_cache(self, feed, fake_session, fake_clock):
        fake_session.queue(kraken_ok("50000.0"))
        assert feed.usd("BTC") == 50000.0
        fake_clock.advance(30)  # within TTL
        assert feed.usd("BTC") == 50000.0
        assert len(fake_session.calls) == 1  # only one HTTP call

    def test_cache_expires_after_ttl(self, feed, fake_session, fake_clock):
        fake_session.queue(kraken_ok("50000.0"), kraken_ok("51000.0"))
        assert feed.usd("BTC") == 50000.0
        fake_clock.advance(61)  # past TTL
        assert feed.usd("BTC") == 51000.0
        assert len(fake_session.calls) == 2

    def test_per_coin_cache_is_independent(self, feed, fake_session):
        fake_session.queue(kraken_ok("50000.0"), kraken_ok("150.0"))
        assert feed.usd("BTC") == 50000.0
        assert feed.usd("XMR") == 150.0
        # Both fetched, neither poisoned the other
        assert len(fake_session.calls) == 2

    def test_clear_cache_forces_refetch(self, feed, fake_session, fake_clock):
        fake_session.queue(kraken_ok("50000.0"), kraken_ok("51000.0"))
        feed.usd("BTC")
        feed.clear_cache()
        assert feed.usd("BTC") == 51000.0
        assert len(fake_session.calls) == 2


# ---------------------------------------------------------------------------
# Failure and stale-fallback behavior
# ---------------------------------------------------------------------------

class TestFailures:
    def test_http_500_raises_when_no_cache(self, feed, fake_session):
        fake_session.queue(http_error(500))
        with pytest.raises(PriceFeedError, match="http 500"):
            feed.usd("BTC")

    def test_kraken_error_field_raises(self, feed, fake_session):
        fake_session.queue(kraken_err("EQuery:Unknown asset pair"))
        with pytest.raises(PriceFeedError, match="kraken error"):
            feed.usd("BTC")

    def test_network_exception_raises(self, feed, fake_session):
        fake_session.queue(requests.ConnectionError("dns fail"))
        with pytest.raises(PriceFeedError, match="request failed"):
            feed.usd("BTC")

    def test_non_json_raises(self, feed, fake_session):
        r = Mock(status_code=200)
        r.json.side_effect = ValueError("no json")
        fake_session.queue(r)
        with pytest.raises(PriceFeedError, match="not valid JSON"):
            feed.usd("BTC")

    def test_malformed_ticker_entry_raises(self, feed, fake_session):
        r = Mock(status_code=200)
        r.json.return_value = {"error": [], "result": {"XXBTZUSD": {}}}
        fake_session.queue(r)
        with pytest.raises(PriceFeedError, match="malformed ticker"):
            feed.usd("BTC")

    def test_non_numeric_price_raises(self, feed, fake_session):
        fake_session.queue(kraken_ok("not-a-number"))
        with pytest.raises(PriceFeedError, match="non-numeric"):
            feed.usd("BTC")

    def test_stale_fallback_within_ceiling(self, feed, fake_session, fake_clock):
        # First fetch works
        fake_session.queue(kraken_ok("50000.0"))
        assert feed.usd("BTC") == 50000.0
        # Past TTL, but within max_stale; fetch fails
        fake_clock.advance(120)
        fake_session.queue(http_error(500))
        assert feed.usd("BTC") == 50000.0  # stale value served

    def test_stale_fallback_expires(self, feed, fake_session, fake_clock):
        fake_session.queue(kraken_ok("50000.0"))
        feed.usd("BTC")
        # Past max_stale; fetch fails; no fallback allowed
        fake_clock.advance(301)
        fake_session.queue(http_error(500))
        with pytest.raises(PriceFeedError, match="http 500"):
            feed.usd("BTC")

    def test_failed_fetch_does_not_poison_cache(self, feed, fake_session, fake_clock):
        fake_session.queue(kraken_ok("50000.0"))
        feed.usd("BTC")
        fake_clock.advance(61)
        # New fetch fails; stale fallback returns 50000
        fake_session.queue(http_error(500))
        assert feed.usd("BTC") == 50000.0
        # Advance a bit more but stay inside TTL of *original* cache timestamp.
        # Cache timestamp is from the original fetch, so TTL already expired.
        # Next call refetches.
        fake_clock.advance(10)
        fake_session.queue(kraken_ok("52000.0"))
        assert feed.usd("BTC") == 52000.0


# ---------------------------------------------------------------------------
# Direct response parsing
# ---------------------------------------------------------------------------

class TestParser:
    def test_parser_reads_c_field(self):
        payload = {"error": [], "result": {"XXBTZUSD": {"c": ["12345.67", "1"]}}}
        assert price_mod._parse_kraken_response(payload, "XXBTZUSD") == 12345.67

    def test_parser_rejects_non_dict(self):
        with pytest.raises(PriceFeedError):
            price_mod._parse_kraken_response("not a dict", "XXBTZUSD")  # type: ignore[arg-type]

    def test_parser_rejects_empty_result(self):
        with pytest.raises(PriceFeedError, match="no result"):
            price_mod._parse_kraken_response({"error": [], "result": {}}, "XXBTZUSD")

    def test_parser_surfaces_kraken_errors(self):
        with pytest.raises(PriceFeedError, match="kraken error"):
            price_mod._parse_kraken_response({"error": ["EGeneral:Invalid"], "result": {}}, "XXBTZUSD")
