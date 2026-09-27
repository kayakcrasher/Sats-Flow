"""Donor account view — donation history, quick links."""
from __future__ import annotations

import time

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from satsflow.storage.db import Database, NotFoundError
from satsflow.storage.models import Donation
from satsflow.web.auth_helpers import current_user
from satsflow.web.templating import templates

router = APIRouter()


def _age(ts: int) -> str:
    delta = int(time.time()) - ts
    if delta < 60:
        return f"{delta}s ago"
    if delta < 3600:
        return f"{delta // 60}m ago"
    if delta < 86400:
        return f"{delta // 3600}h ago"
    return f"{delta // 86400}d ago"


def _donation_row(db: Database, d: Donation) -> dict:
    try:
        recipient = db.get_user(d.user_id)
        recipient_name = recipient.display_name
        recipient_slug = recipient.slug
    except NotFoundError:
        recipient_name = "Unknown"
        recipient_slug = ""

    return {
        "id": d.id,
        "recipient_name": recipient_name,
        "recipient_slug": recipient_slug,
        "coin": d.coin,
        "amount": d.amount,
        "usd": d.usd_at_receipt,
        "message": d.message,
        "age": _age(d.created_at),
        "txid": d.txid,
        "confirmed": d.confirmed_at is not None,
    }


@router.get("/me", response_class=HTMLResponse)
async def me(request: Request):
    user = current_user(request)
    if user is None:
        return RedirectResponse(url="/auth/login", status_code=303)

    db: Database = request.app.state.db

    donations = db.list_donations_by_donor(user.id, limit=100) if user.id else []
    rows = [_donation_row(db, d) for d in donations]

    total_btc_sats = sum(d.amount for d in donations if d.coin == "BTC")
    total_xmr_pico = sum(d.amount for d in donations if d.coin == "XMR")
    total_usd = sum((d.usd_at_receipt or 0.0) for d in donations)

    return templates.TemplateResponse(
        request=request,
        name="me.html",
        context={
            "user": {
                "slug": user.slug,
                "display_name": user.display_name,
                "is_creator": user.is_creator,
            },
            "donations": rows,
            "totals": {
                "count": len(rows),
                "btc_sats": total_btc_sats,
                "xmr_piconero": total_xmr_pico,
                "usd": total_usd,
            },
            "active": "me",
        },
    )
