"""Public user donation page routes — reads from the database."""
from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from satsflow.storage.db import Database, NotFoundError
from satsflow.storage.models import Donation
from satsflow.web.templating import templates

router = APIRouter(prefix="/c")


def _age(ts: int) -> str:
    delta = int(time.time()) - ts
    if delta < 60:
        return f"{delta}s"
    if delta < 3600:
        return f"{delta // 60}m"
    if delta < 86400:
        return f"{delta // 3600}h"
    return f"{delta // 86400}d"


def _donation_to_feed(d: Donation) -> dict:
    return {
        "name": d.donor_name,
        "amount": d.amount,
        "coin": d.coin,
        "age": _age(d.created_at),
        "message": d.message,
        "txid": d.txid or ("0" * 64),
    }


@router.get("")
@router.get("/")
async def creator_root() -> Response:
    return RedirectResponse(url="/explore", status_code=303)


@router.get("/{slug}", response_class=HTMLResponse)
async def user_page(request: Request, slug: str) -> HTMLResponse:
    db: Database = request.app.state.db

    try:
        user = db.get_user_by_slug(slug)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="User not found") from None

    if user.id is None:
        raise HTTPException(status_code=500, detail="user id missing")

    donations = db.list_donations(user.id, limit=20)

    btc_sats = sum(d.amount for d in donations if d.coin == "BTC")
    xmr_pico = sum(d.amount for d in donations if d.coin == "XMR")

    user_ctx = {
        "slug": user.slug,
        "display_name": user.display_name,
        "bio": user.bio,
        "received_sats": btc_sats,
        "received_piconero": xmr_pico,
        "donation_count": len(donations),
    }

    return templates.TemplateResponse(
        request=request,
        name="creator.html",
        context={
            "creator": user_ctx,
            "user": user_ctx,
            "feed": [_donation_to_feed(d) for d in donations],
            "active": "user",
        },
    )
