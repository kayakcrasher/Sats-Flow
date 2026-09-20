"""Kraken public ticker price feed with in-memory cache."""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

import requests

KRAKEN_TICKER_URL = "https://api.kraken.com/0/public/Ticker"
REQUEST_TIMEOUT = 5.0
MAX_STALE_SECONDS = 300

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
    if not isinstance(payload, dict):
        raise PriceFeedError("malformed response: not a dict")
    if payload.get("error"):
        raise PriceFeedError(f"kraken error: {payload['error']}")
    result = payload.get("result")
    if not isinstance(result, dict) or not result:
        raise PriceFeedError("malformed response: no result")
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
    cache_ttl: float = 60.0
    max_stale: float = MAX_STALE_SECONDS
    session: requests.Session = field(default_factory=requests.Session)
    clock: Callable[[], float] = time.time
    _cache: dict[str, _CacheEntry] = field(default_factory=dict, init=False)

    def usd(self, coin: str) -> float:
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
        self._cache.clear()
