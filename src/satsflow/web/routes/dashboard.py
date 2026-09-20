"""Creator dashboard route. Auth and real data come later."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from satsflow.web.app import templates

router = APIRouter()


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    donations = [
        {"txid": "a1b2c3d4e5f6", "amount_sats": 2_500_000, "usd": 168.42, "coin": "BTC", "age": "2m"},
        {"txid": "f6e5d4c3b2a1", "amount_sats": 500_000, "usd": 33.68, "coin": "BTC", "age": "18m"},
        {"txid": "x1y2z3w4v5u6", "amount_sats": 1_250_000, "usd": 84.21, "coin": "BTC", "age": "1h"},
        {"txid": "q7r8s9t0u1v2", "amount_sats": 250_000, "usd": 16.84, "coin": "BTC", "age": "4h"},
    ]
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={"donations": donations, "active": "dashboard"},
    )
