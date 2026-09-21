"""Public price endpoint for the donate form.

Returns the current USD price for a coin. Cached 60s server-side by
PriceFeed, so hammering this route is cheap.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from satsflow.core.price import PriceFeed, PriceFeedError

router = APIRouter()

# One shared feed for the process — keeps the 60s cache warm.
_feed = PriceFeed()


@router.get("/api/price")
async def get_price(coin: str = Query(..., min_length=3, max_length=3)) -> dict:
    """Return {"coin": "BTC", "usd": 50000.0} for the requested coin."""
    coin = coin.upper()
    if coin not in ("BTC", "XMR"):
        raise HTTPException(status_code=400, detail="unsupported coin")

    try:
        price = _feed.usd(coin)
    except PriceFeedError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {"coin": coin, "usd": price}
