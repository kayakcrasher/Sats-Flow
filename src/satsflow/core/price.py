"""Kraken public ticker price feed with in-memory cache.

Why Kraken:
  - No API key required for public ticker
  - Generous rate limits at our scale
  - Returns BTC/USD and XMR/USD in the same endpoint shape
  - Battle-tested exchange infrastructure

Design:
  - PriceFeed is stateful: it holds a small in-memory cache.
  - usd(coin) returns the last traded price for COIN/USD.
  - Cache TTL (default 60s) prevents hammering Kraken per invoice.
  - On failure, falls back to the last cached value up to a hard ceiling,
    then raises. Never silently returns a stale price beyond the ceiling.
  - Fees are always calculated on-chain in sats/piconero. USD is used for
    display and for USD-denominated invoices only.

Kraken pair naming:
  BTC/USD -> "XXBTZUSD"
  XMR/USD -> "XXMRZUSD"
The result dict keys the response by these names, not the human pair.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

import requests

# --- Config ----------------------------------------------------------------

KRAKEN_TICKER_URL = "https://api.kraken.com/0/public/Ticker"
REQUEST_TIMEOUT = 5.0  # seconds

# Hard ceiling on how stale a cached price may be when Kraken is down.
# Past this, usd() raises instead of returning a misleading number.
MAX_STALE_SECONDS = 300  # 5 minutes

# Kraken pair name map. Keys are our internal coin symbols.
_PAIR_MAP = {
    "BTC": "XXBTZUSD",
    "XMR": "XXMRZUSD",
}


class PriceFeedError(Exception):
    """Raised when a price cannot be fetched and no acceptable cache exists."""


@dataclass
class _CacheEntry:
    price: float
    timestamp: float


def _kraken_pair(coin: str) -> str:
    coin = coin.upper()
    try:
        return _PAIR_MAP[coin]
    except KeyError as exc:
        raise PriceFeedError(f"unsupported coin: {coin}") from exc


def _parse_kraken_response(payload: dict, pair: str) -> float:
    """Extract last-trade price from a Kraken Ticker response.

    Kraken returns:
        {"error": [], "result": {"XXBTZUSD": {"c": ["50000.0", "0.001"], ...}}}
    The 'c' field is [last_trade_price, last_trade_volume].
    """
    if not isinstance(payload, dict):
        raise PriceFeedError("malformed response: not a dict")
    if payload.get("error"):
        raise PriceFeedError(f"kraken error: {payload['error']}")
    result = payload.get("result")
    if not isinstance(result, dict) or not result:
        raise PriceFeedError("malformed response: no result")

    # Kraken sometimes keys by a slightly different alias; take the first entry.
    entry = next(iter(result.values()))
    try:
        last_price = entry["c"][0]
    except (KeyError, IndexError, TypeError) as exc:
        raise PriceFeedError("malformed ticker entry") from exc

    try:
        return float(last_price)
    except (TypeError, ValueError) as exc:
        raise PriceFeedError(f"non-numeric price: {last_price!r}") from exc


@dataclass
class PriceFeed:
    """In-memory cached price feed backed by Kraken's public Ticker endpoint.

    Args:
        cache_ttl: seconds a cached price is considered fresh
        max_stale: seconds a cached price may be used as a fallback if fetch fails
        session:   requests.Session for connection pooling (tests inject a stub)
        clock:     callable returning current unix time (tests inject a fake)
    """

    cache_ttl: float = 60.0
    max_stale: float = MAX_STALE_SECONDS
    session: requests.Session = field(default_factory=requests.Session)
    clock: Callable[[], float] = time.time
    _cache: dict[str, _CacheEntry] = field(default_factory=dict, init=False)

    def usd(self, coin: str) -> float:
        """Return the current COIN/USD price. Raises PriceFeedError on failure."""
        coin = coin.upper()
        pair = _kraken_pair(coin)
        now = self.clock()

        cached = self._cache.get(coin)
        if cached and (now - cached.timestamp) < self.cache_ttl:
            return cached.price

        try:
            price = self._fetch(pair)
        except PriceFeedError:
            if cached and (now - cached.timestamp) < self.max_stale:
                return cached.price
            raise

        self._cache[coin] = _CacheEntry(price=price, timestamp=now)
        return price

    def _fetch(self, pair: str) -> float:
        try:
            resp = self.session.get(
                KRAKEN_TICKER_URL,
                params={"pair": pair},
                timeout=REQUEST_TIMEOUT,
            )
        except requests.RequestException as exc:
            raise PriceFeedError(f"request failed: {exc}") from exc

        if resp.status_code != 200:
            raise PriceFeedError(f"http {resp.status_code}")

        try:
            payload = resp.json()
        except ValueError as exc:
            raise PriceFeedError("response is not valid JSON") from exc

        return _parse_kraken_response(payload, pair)

    def clear_cache(self) -> None:
        """Drop cached prices. Useful after a config change or manual refresh."""
        self._cache.clear()
