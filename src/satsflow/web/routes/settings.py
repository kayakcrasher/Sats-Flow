"""Creator settings: edit profile, change password, set xpub."""
from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from satsflow.security.passwords import hash_password, verify_password
from satsflow.storage.db import Database
from satsflow.web.auth_helpers import current_creator
from satsflow.web.templating import templates

router = APIRouter()


def _creator_ctx(c) -> dict:
    return {
        "slug": c.slug,
        "display_name": c.display_name,
        "bio": c.bio,
        "btc_address": c.btc_address or "",
        "xmr_address": c.xmr_address or "",
        "btc_xpub": c.btc_xpub or "",
    }


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    creator = current_creator(request)
    if creator is None:
        return RedirectResponse(url="/auth/login", status_code=303)

    return templates.TemplateResponse(
        request=request,
        name="settings.html",
        context={
            "creator": _creator_ctx(creator),
            "active": "settings",
            "error": None,
        },
    )


@router.post("/settings/profile")
async def update_profile(
    request: Request,
    display_name: str = Form(...),
    bio: str = Form(""),
    btc_address: str = Form(""),
    xmr_address: str = Form(""),
    btc_xpub: str = Form(""),
):
    creator = current_creator(request)
    if creator is None:
        return RedirectResponse(url="/auth/login", status_code=303)

    db: Database = request.app.state.db
    xpub = btc_xpub.strip() or None

    # Validate xpub if provided
    if xpub:
        from satsflow.core.bip32 import Bip32Error, parse_xpub
        try:
            parse_xpub(xpub)
        except Bip32Error:
            return templates.TemplateResponse(
                request=request,
                name="settings.html",
                context={
                    "creator": {
                        "slug": creator.slug,
                        "display_name": display_name.strip(),
                        "bio": bio.strip(),
                        "btc_address": btc_address.strip(),
                        "xmr_address": xmr_address.strip(),
                        "btc_xpub": xpub or "",
                    },
                    "active": "settings",
                    "error": "That xpub doesn't look valid. Copy it exactly from your wallet.",
                },
                status_code=400,
            )

    db._conn.execute(
        """UPDATE creators
           SET display_name = ?, bio = ?, btc_address = ?, xmr_address = ?, btc_xpub = ?
           WHERE id = ?""",
        (
            display_name.strip(),
            bio.strip(),
            btc_address.strip() or None,
            xmr_address.strip() or None,
            xpub,
            creator.id,
        ),
    )
    db._conn.commit()

    return RedirectResponse(url="/settings?saved=1", status_code=303)


@router.post("/settings/password")
async def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
):
    creator = current_creator(request)
    if creator is None:
        return RedirectResponse(url="/auth/login", status_code=303)

    if not creator.password_hash or not verify_password(creator.password_hash, current_password):
        return templates.TemplateResponse(
            request=request,
            name="settings.html",
            context={
                "creator": _creator_ctx(creator),
                "active": "settings",
                "error": "Current password is incorrect.",
            },
            status_code=400,
        )

    if len(new_password) < 8:
        return templates.TemplateResponse(
            request=request,
            name="settings.html",
            context={
                "creator": _creator_ctx(creator),
                "active": "settings",
                "error": "New password must be at least 8 characters.",
            },
            status_code=400,
        )

    db: Database = request.app.state.db
    db._conn.execute(
        "UPDATE creators SET password_hash = ? WHERE id = ?",
        (hash_password(new_password), creator.id),
    )
    db._conn.commit()

    return RedirectResponse(url="/settings?changed=1", status_code=303)
