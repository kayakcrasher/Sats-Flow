"""Join page — the fork between becoming a creator and donating only."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from satsflow.web.auth_helpers import current_user
from satsflow.web.templating import templates

router = APIRouter()


@router.get("/join", response_class=HTMLResponse)
async def join(request: Request) -> Response:
    # Already logged in? Send them where they'd want to go.
    user = current_user(request)
    if user is not None:
        target = "/dashboard" if user.is_creator else "/me"
        return RedirectResponse(url=target, status_code=303)

    return templates.TemplateResponse(
        request=request,
        name="join.html",
        context={"active": "join"},
    )
