"""Creator dashboard route. Auth and real data come later."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from satsflow.web.templating import templates

router = APIRouter()


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    donations = [
        {"name": "anon_sats", "message": "Great stream tonight! Keep it up.",
         "txid": "a1b2c3d4e5f6a7b8", "amount_sats": 2_500_000, "usd": 168.42,
         "coin": "BTC", "age": "2m"},
        {"name": None, "message": None,
         "txid": "f6e5d4c3b2a1f0e9", "amount_sats": 500_000, "usd": 33.68,
         "coin": "BTC", "age": "18m"},
        {"name": "monero_fan", "message": "Been following since day one.",
         "txid": "x1y2z3w4v5u6t7s8", "amount_sats": 1_250_000, "usd": 84.21,
         "coin": "BTC", "age": "1h"},
        {"name": "quiet_donor", "message": None,
         "txid": "q7r8s9t0u1v2w3x4", "amount_sats": 250_000, "usd": 16.84,
         "coin": "BTC", "age": "4h"},
    ]
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={"donations": donations, "active": "dashboard"},
    )
