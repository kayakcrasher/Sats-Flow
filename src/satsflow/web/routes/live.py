"""Live donation wall — Superchat mode.

Shows every donation for a creator in the last 24h, newest first.
Auto-refreshes every 10 seconds via HTMX. Built for streamers to run
as an OBS browser-source overlay.
"""
from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from satsflow.storage.db import Database, NotFoundError
from satsflow.storage.models import Donation
from satsflow.web.templating import templates

router = APIRouter(prefix="/c")

WINDOW_SECONDS = 24 * 60 * 60  # 24 hours


def _age(ts: int) -> str:
    delta = int(time.time()) - ts
    if delta < 60:
        return f"{delta}s ago"
    if delta < 3600:
        return f"{delta // 60}m ago"
    if delta < 86400:
        return f"{delta // 3600}h ago"
    return f"{delta // 86400}d ago"


def _row(d: Donation) -> dict:
    return {
        "id": d.id,
        "name": d.donor_name,
        "coin": d.coin,
        "amount": d.amount,
        "message": d.message,
        "age": _age(d.created_at),
        "confirmed": d.confirmed_at is not None,
        "txid": d.txid,
    }


def _load(db: Database, slug: str) -> tuple[dict, list[dict], dict]:
    try:
        creator = db.get_creator_by_slug(slug)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Creator not found") from None

    since = int(time.time()) - WINDOW_SECONDS
    donations = db.list_donations_since(creator.id, since, limit=500)

    totals = {
        "count": len(donations),
        "btc": sum(d.amount for d in donations if d.coin == "BTC"),
        "xmr": sum(d.amount for d in donations if d.coin == "XMR"),
        "with_messages": sum(1 for d in donations if d.message),
    }

    creator_ctx = {
        "slug": creator.slug,
        "display_name": creator.display_name,
        "btc_address": creator.btc_address,
        "xmr_address": creator.xmr_address,
    }

    return creator_ctx, [_row(d) for d in donations], totals


@router.get("/{slug}/live", response_class=HTMLResponse)
async def live_wall(request: Request, slug: str) -> HTMLResponse:
    """Full-page superchat wall."""
    db: Database = request.app.state.db
    creator, donations, totals = _load(db, slug)
    return templates.TemplateResponse(
        request=request,
        name="live.html",
        context={
            "creator": creator,
            "donations": donations,
            "totals": totals,
            "active": "creator",
        },
    )


@router.get("/{slug}/live/feed", response_class=HTMLResponse)
async def live_feed(request: Request, slug: str) -> HTMLResponse:
    """HTMX partial — just the donation list, polled every 10s."""
    db: Database = request.app.state.db
    creator, donations, totals = _load(db, slug)
    return templates.TemplateResponse(
        request=request,
        name="partials/live_feed.html",
        context={
            "creator": creator,
            "donations": donations,
            "totals": totals,
        },
    )
