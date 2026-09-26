"""Creator dashboard route — shows the logged-in creator's data."""
from __future__ import annotations

import csv
import io
import time
from datetime import UTC, datetime

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse

from satsflow.core.fees import (
    days_until_next_tier,
    fee_percent_for,
    tier_name,
)
from satsflow.storage.db import Database
from satsflow.storage.models import Creator, Donation
from satsflow.web.auth_helpers import current_creator
from satsflow.web.templating import templates

router = APIRouter()


def _age(ts: int) -> str:
    delta = int(time.time()) - ts
    if delta < 60:
        return f"{delta}s"
    if delta < 3600:
        return f"{delta // 60}m"
    if delta < 86400:
        return f"{delta // 3600}h"
    return f"{delta // 86400}d"


def _donation_row(d: Donation) -> dict:
    return {
        "name": d.donor_name,
        "message": d.message,
        "coin": d.coin,
        "amount_sats": d.amount,
        "usd": d.usd_at_receipt or 0.0,
        "age": _age(d.created_at),
        "txid": d.txid or ("0" * 64),
    }


def _load(db: Database, creator: Creator) -> tuple[list[Donation], dict]:
    if creator.id is None:
        return [], {"btc": 0, "xmr": 0, "count": 0, "unread": 0}
    donations = db.list_donations(creator.id, limit=50)
    btc_sats = sum(d.amount for d in donations if d.coin == "BTC")
    xmr_pico = sum(d.amount for d in donations if d.coin == "XMR")
    unread = sum(1 for d in donations if d.message)
    return donations, {
        "btc": btc_sats,
        "xmr": xmr_pico,
        "count": len(donations),
        "unread": unread,
    }


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    creator = current_creator(request)
    if creator is None:
        return RedirectResponse(url="/auth/login", status_code=303)

    db: Database = request.app.state.db
    donations, totals = _load(db, creator)

    fee_pct = fee_percent_for(creator.created_at, override=creator.fee_override)
    fee_ctx = {
        "percent": fee_pct,
        "display_percent": f"{fee_pct * 100:.1f}%",
        "tier": tier_name(creator.created_at, override=creator.fee_override),
        "days_until_drop": days_until_next_tier(
            creator.created_at, override=creator.fee_override
        ),
        "balance_sats": creator.fee_balance_sats,
    }

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "creator": {
                "slug": creator.slug,
                "display_name": creator.display_name,
            },
            "donations": [_donation_row(d) for d in donations],
            "totals": totals,
            "fee": fee_ctx,
            "active": "dashboard",
        },
    )


@router.get("/dashboard/export.csv")
async def export_csv(request: Request):
    """Stream the logged-in creator's donations as a CSV download."""
    creator = current_creator(request)
    if creator is None:
        return RedirectResponse(url="/auth/login", status_code=303)

    db: Database = request.app.state.db

    if creator.id is None:
        donations: list[Donation] = []
    else:
        donations = db.list_donations(creator.id, limit=10_000)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "created_at_utc", "coin", "amount", "usd_at_receipt",
        "donor_name", "message", "txid", "confirmed_at_utc",
    ])
    for d in donations:
        writer.writerow([
            datetime.fromtimestamp(d.created_at, tz=UTC).isoformat(),
            d.coin,
            d.amount,
            d.usd_at_receipt if d.usd_at_receipt is not None else "",
            d.donor_name or "",
            d.message or "",
            d.txid or "",
            (
                datetime.fromtimestamp(d.confirmed_at, tz=UTC).isoformat()
                if d.confirmed_at
                else ""
            ),
        ])

    buf.seek(0)
    filename = f"satsflow-{creator.slug}-{datetime.now(UTC):%Y%m%d}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

@router.get("/dashboard/settle", response_class=HTMLResponse)
async def settle_page(request: Request):
    """Show the fee settlement invoice: platform address, QR, amount."""
    creator = current_creator(request)
    if creator is None:
        return RedirectResponse(url="/auth/login", status_code=303)

    if creator.fee_balance_sats <= 0:
        return RedirectResponse(url="/dashboard", status_code=303)

    from satsflow import config
    from satsflow.web.qr import btc_uri, qr_svg_data_uri

    dest = config.GNOME_BTC_ADDRESS or creator.btc_address or ""
    if not dest:
        raise HTTPException(
            status_code=500,
            detail="No platform BTC address configured. Set SATFLOW_GNOME_BTC_ADDRESS.",
        )

    qr_data_uri = None
    pay_uri = btc_uri(dest, creator.fee_balance_sats)
    try:
        qr_data_uri = qr_svg_data_uri(pay_uri)
    except (ValueError, TypeError):
        qr_data_uri = None

    return templates.TemplateResponse(
        request=request,
        name="settle.html",
        context={
            "creator": {
                "slug": creator.slug,
                "display_name": creator.display_name,
            },
            "balance_sats": creator.fee_balance_sats,
            "address": dest,
            "qr_data_uri": qr_data_uri,
            "pay_uri": pay_uri,
            "active": "dashboard",
        },
    )


@router.post("/dashboard/settle/confirm")
async def settle_confirm(request: Request, txid: str = Form(...)):
    """Creator pastes the txid they used to pay. We record and reset."""
    creator = current_creator(request)
    if creator is None:
        return RedirectResponse(url="/auth/login", status_code=303)

    if creator.id is None:
        raise HTTPException(status_code=500, detail="creator id missing")

    txid = txid.strip()
    if len(txid) < 10 or len(txid) > 128:
        raise HTTPException(status_code=400, detail="Invalid txid")

    db: Database = request.app.state.db

    from satsflow import config
    db.record_settlement(
        creator.id,
        creator.fee_balance_sats,
        txid=txid,
        address=config.GNOME_BTC_ADDRESS or None,
    )
    db.reset_fee_balance(creator.id)

    return RedirectResponse(url="/dashboard?settled=1", status_code=303)
