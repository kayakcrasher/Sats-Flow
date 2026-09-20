"""Public creator donation page routes.

Real data wiring comes in Phase 6 (storage). For now, mock data so the
template renders meaningfully during design iteration.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from satsflow.web.app import templates

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


@router.get("/{slug}", response_class=HTMLResponse)
async def creator_page(request: Request, slug: str) -> HTMLResponse:
    creator = _MOCK_CREATORS.get(slug)
    if creator is None:
        raise HTTPException(status_code=404, detail="Creator not found")
    return templates.TemplateResponse(
        request=request,
        name="creator.html",
        context={"creator": creator, "active": "creator"},
    )
