"""Donate flow: create an invoice, show the address, wait for payment."""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from satsflow.core.bitcoin import Bitcoin, BitcoinError
from satsflow.core.fees import fee_percent_for
from satsflow.core.monero import Monero, MoneroError, xmr_to_piconero
from satsflow.core.payment_watcher import PaymentWatcher, WatchError
from satsflow.storage.db import Database, NotFoundError
from satsflow.web.qr import btc_uri, qr_svg_data_uri, xmr_uri
from satsflow.web.templating import templates

router = APIRouter(prefix="/c")


def _load_btc() -> Bitcoin:
    return Bitcoin()


def _load_xmr() -> Monero:
    return Monero()


@router.post("/{slug}/donate")
async def create_invoice(
    request: Request,
    slug: str,
    coin: str = Form(...),
    amount_crypto: str = Form(""),
    amount_usd: str = Form(""),
    display_name: str = Form(""),
    message: str = Form(""),
) -> RedirectResponse:
    """Create a pending donation + a fresh receive address."""
    db: Database = request.app.state.db

    try:
        creator = db.get_creator_by_slug(slug)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Creator not found") from None

    if creator.id is None:
        raise HTTPException(status_code=500, detail="Creator id missing")

    coin = coin.upper()
    if coin not in ("BTC", "XMR"):
        raise HTTPException(status_code=400, detail="Unsupported coin")

    # Amount: prefer explicit crypto amount; else fall back to USD placeholder.
    amount_int: int
    try:
        if amount_crypto.strip():
            if coin == "BTC":
                amount_int = round(float(amount_crypto) * 100_000_000)
            else:
                amount_int = xmr_to_piconero(float(amount_crypto))
        elif amount_usd.strip():
            from satsflow.core.price import PriceFeed, PriceFeedError
            try:
                price = PriceFeed().usd(coin)
            except PriceFeedError as exc:
                raise HTTPException(
                    status_code=502, detail=f"price feed unavailable: {exc}"
                ) from None
            usd_val = float(amount_usd)
            if price <= 0:
                raise ValueError("invalid price feed")
            crypto_val = usd_val / price
            if coin == "BTC":
                amount_int = round(crypto_val * 100_000_000)
            else:
                amount_int = xmr_to_piconero(crypto_val)
        else:
            raise ValueError("no amount provided")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid amount: {exc}") from None

    if amount_int < 0:
        raise HTTPException(status_code=400, detail="amount must be non-negative")

    # Generate a fresh receive address from the appropriate backend.
    label = f"inv-{slug}-{secrets.token_hex(4)}"
    try:
        if coin == "BTC":
            btc = Bitcoin(xpub=creator.btc_xpub)
            address = btc.new_address(label)
        else:
            address = _load_xmr().new_address(label)
    except (BitcoinError, MoneroError) as exc:
        raise HTTPException(status_code=502, detail=f"address generation failed: {exc}") from None

    # Snapshot the creator's fee percent at the moment of donation.
    fee_pct = fee_percent_for(creator.created_at, override=creator.fee_override)
    platform_fee = int(amount_int * fee_pct)

    donation = db.create_donation(
        creator_id=creator.id,
        coin=coin,
        amount=amount_int,
        usd_at_receipt=float(amount_usd) if amount_usd.strip() else None,
        address=address,
        donor_name=(display_name.strip() or None),
        message=(message.strip() or None),
        platform_fee_sats=platform_fee,
        fee_percent_at_creation=fee_pct,
    )

    return RedirectResponse(url=f"/c/{slug}/invoice/{donation.id}", status_code=303)


@router.get("/{slug}/invoice/{donation_id}", response_class=HTMLResponse)
async def show_invoice(
    request: Request,
    slug: str,
    donation_id: int,
) -> HTMLResponse:
    """Show the invoice: address, amount, and payment instructions."""
    db: Database = request.app.state.db

    try:
        creator = db.get_creator_by_slug(slug)
        donation = db.get_donation(donation_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Invoice not found") from None

    if donation.creator_id != creator.id:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # Build a payment URI + QR code for wallets that scan.
    qr_data_uri = None
    pay_uri = None
    if donation.address:
        if donation.coin == "BTC":
            pay_uri = btc_uri(donation.address, donation.amount)
        else:
            pay_uri = xmr_uri(donation.address, donation.amount)
        try:
            qr_data_uri = qr_svg_data_uri(pay_uri)
        except (ValueError, TypeError):
            qr_data_uri = None

    return templates.TemplateResponse(
        request=request,
        name="invoice.html",
        context={
            "creator": {
                "slug": creator.slug,
                "display_name": creator.display_name,
            },
            "donation": {
                "id": donation.id,
                "coin": donation.coin,
                "amount": donation.amount,
                "usd": donation.usd_at_receipt,
                "address": donation.address,
                "donor_name": donation.donor_name,
                "message": donation.message,
            },
            "qr_data_uri": qr_data_uri,
            "pay_uri": pay_uri,
            "active": "creator",
        },
    )

@router.get("/{slug}/invoice/{donation_id}/status")
async def invoice_status(
    request: Request,
    slug: str,
    donation_id: int,
) -> dict:
    """Return the current payment status as JSON. Called by the invoice page."""
    db: Database = request.app.state.db

    try:
        creator = db.get_creator_by_slug(slug)
        donation = db.get_donation(donation_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Invoice not found") from None

    if donation.creator_id != creator.id:
        raise HTTPException(status_code=404, detail="Invoice not found")

    watcher: PaymentWatcher = request.app.state.watcher
    try:
        result = watcher.check(donation_id)
    except WatchError as exc:
        return {"status": "error", "error": str(exc)}

    return {
        "status": result.status,
        "received": result.received,
        "expected": result.expected,
        "confirmations": result.confirmations,
        "txid": result.txid,
        "is_final": result.is_final,
    }
