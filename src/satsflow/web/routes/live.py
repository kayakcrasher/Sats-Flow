"""Live donation wall — Superchat mode."""
from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse

from satsflow.storage.db import Database, NotFoundError
from satsflow.storage.models import Donation
from satsflow.web.auth_helpers import current_creator
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
        "pinned": d.pinned,
        "read": d.read_at is not None,
    }


def _load(db: Database, slug: str, min_amount: int = 0) -> tuple[dict, list[dict], dict, bool]:
    try:
        creator = db.get_creator_by_slug(slug)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Creator not found") from None

    if creator.id is None:
        raise HTTPException(status_code=500, detail="creator id missing")

    since = int(time.time()) - WINDOW_SECONDS
    donations = db.list_donations_since_filtered(
        creator.id, since, min_amount=min_amount, limit=500
    )

    totals = {
        "count": len(donations),
        "btc": sum(d.amount for d in donations if d.coin == "BTC"),
        "xmr": sum(d.amount for d in donations if d.coin == "XMR"),
        "with_messages": sum(1 for d in donations if d.message),
        "unread": db.count_unread(creator.id),
    }

    creator_ctx = {
        "slug": creator.slug,
        "display_name": creator.display_name,
        "btc_address": creator.btc_address,
        "xmr_address": creator.xmr_address,
    }

    return creator_ctx, [_row(d) for d in donations], totals, False


@router.get("/{slug}/live", response_class=HTMLResponse)
async def live_wall(
    request: Request,
    slug: str,
    min_amount: int = Query(0, ge=0),
) -> HTMLResponse:
    db: Database = request.app.state.db
    creator, donations, totals, _ = _load(db, slug, min_amount)
    me = current_creator(request)
    is_owner = me is not None and me.slug == slug
    return templates.TemplateResponse(
        request=request,
        name="live.html",
        context={
            "creator": creator,
            "donations": donations,
            "totals": totals,
            "min_amount": min_amount,
            "is_owner": is_owner,
            "active": "creator",
        },
    )


@router.get("/{slug}/live/feed", response_class=HTMLResponse)
async def live_feed(
    request: Request,
    slug: str,
    min_amount: int = Query(0, ge=0),
) -> HTMLResponse:
    db: Database = request.app.state.db
    creator, donations, totals, _ = _load(db, slug, min_amount)
    me = current_creator(request)
    is_owner = me is not None and me.slug == slug
    return templates.TemplateResponse(
        request=request,
        name="partials/live_feed.html",
        context={
            "creator": creator,
            "donations": donations,
            "totals": totals,
            "min_amount": min_amount,
            "is_owner": is_owner,
        },
    )


# --- Owner-only actions ---------------------------------------------------

def _require_owner(request: Request, slug: str) -> None:
    me = current_creator(request)
    if me is None or me.slug != slug:
        raise HTTPException(status_code=403, detail="Not your live wall")


@router.post("/{slug}/live/pin/{donation_id}")
async def pin_donation(request: Request, slug: str, donation_id: int) -> JSONResponse:
    _require_owner(request, slug)
    db: Database = request.app.state.db
    try:
        current = db.get_donation(donation_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Donation not found") from None
    updated = db.set_pinned(donation_id, not current.pinned)
    return JSONResponse({"id": updated.id, "pinned": updated.pinned})


@router.post("/{slug}/live/read/{donation_id}")
async def mark_donation_read(request: Request, slug: str, donation_id: int) -> JSONResponse:
    _require_owner(request, slug)
    db: Database = request.app.state.db
    try:
        updated = db.mark_read(donation_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Donation not found") from None
    return JSONResponse({"id": updated.id, "read": updated.read_at is not None})
