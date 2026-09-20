"""Public creator donation page routes. Mock data for now."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from satsflow.web.templating import templates

router = APIRouter(prefix="/c")


_MOCK_CREATORS: dict[str, dict] = {
    "kayakcrasher": {
        "slug": "kayakcrasher",
        "display_name": "Kayak Crasher",
        "bio": "Building SatsFlow in the open. Tips fund late-night dev sessions.",
        "btc_address": "bc1qexampleaddressxxxxxxxxxxxxxxxxxxxxxxxx",
        "xmr_address": "4examplexmrxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        "received_sats": 128_450_000,
        "received_piconero": 12_500_000_000_000,
        "donation_count": 47,
    },
}

_MOCK_FEED = [
    {"name": "anon_sats", "amount": 250_000, "coin": "BTC", "age": "2m",
     "message": "Great stream tonight! Keep it up.",
     "txid": "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2"},
    {"name": None, "amount": 500_000, "coin": "BTC", "age": "18m",
     "message": None,
     "txid": "f6e5d4c3b2a1f0e9d8c7b6a5f4e3d2c1b0a9f8e7d6c5b4a3f2e1d0c9b8a7f6e5"},
    {"name": "monero_fan", "amount": 1_250_000, "coin": "BTC", "age": "1h",
     "message": "Been following since day one. Sent some sats.",
     "txid": "1111111111111111111111111111111111111111111111111111111111111111"},
]


@router.get("/{slug}", response_class=HTMLResponse)
async def creator_page(request: Request, slug: str) -> HTMLResponse:
    creator = _MOCK_CREATORS.get(slug)
    if creator is None:
        raise HTTPException(status_code=404, detail="Creator not found")
    return templates.TemplateResponse(
        request=request,
        name="creator.html",
        context={"creator": creator, "feed": _MOCK_FEED, "active": "creator"},
    )
