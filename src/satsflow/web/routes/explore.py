"""Public directory of all creators."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from satsflow.storage.db import Database
from satsflow.web.templating import templates

router = APIRouter()


@router.get("/explore", response_class=HTMLResponse)
async def explore(request: Request) -> HTMLResponse:
    db: Database = request.app.state.db
    creators = db.list_creators()

    rows = []
    for c in creators:
        if c.id is None:
            continue
        donations = db.list_donations(c.id, limit=200)
        btc_sats = sum(d.amount for d in donations if d.coin == "BTC")
        xmr_pico = sum(d.amount for d in donations if d.coin == "XMR")
        rows.append({
            "slug": c.slug,
            "display_name": c.display_name,
            "bio": c.bio,
            "donation_count": len(donations),
            "btc_sats": btc_sats,
            "xmr_piconero": xmr_pico,
            "has_btc": bool(c.btc_address),
            "has_xmr": bool(c.xmr_address),
        })

    return templates.TemplateResponse(
        request=request,
        name="explore.html",
        context={"creators": rows, "active": "explore"},
    )
