"""Creator settings: edit profile, change password."""
from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from satsflow.security.passwords import hash_password, verify_password
from satsflow.storage.db import Database
from satsflow.web.auth_helpers import current_creator
from satsflow.web.templating import templates

router = APIRouter()


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    creator = current_creator(request)
    if creator is None:
        return RedirectResponse(url="/auth/login", status_code=303)

    return templates.TemplateResponse(
        request=request,
        name="settings.html",
        context={
            "creator": {
                "slug": creator.slug,
                "display_name": creator.display_name,
                "bio": creator.bio,
                "btc_address": creator.btc_address or "",
                "xmr_address": creator.xmr_address or "",
            },
            "active": "settings",
            "error": None,
            "success": None,
        },
    )


@router.post("/settings/profile")
async def update_profile(
    request: Request,
    display_name: str = Form(...),
    bio: str = Form(""),
    btc_address: str = Form(""),
    xmr_address: str = Form(""),
):
    creator = current_creator(request)
    if creator is None:
        return RedirectResponse(url="/auth/login", status_code=303)

    db: Database = request.app.state.db
    db._conn.execute(
        """UPDATE creators
           SET display_name = ?, bio = ?, btc_address = ?, xmr_address = ?
           WHERE id = ?""",
        (
            display_name.strip(),
            bio.strip(),
            btc_address.strip() or None,
            xmr_address.strip() or None,
            creator.id,
        ),
    )
    db._conn.commit()

    return RedirectResponse(url="/settings", status_code=303)


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
                "creator": {
                    "slug": creator.slug,
                    "display_name": creator.display_name,
                    "bio": creator.bio,
                    "btc_address": creator.btc_address or "",
                    "xmr_address": creator.xmr_address or "",
                },
                "active": "settings",
                "error": "Current password is incorrect.",
                "success": None,
            },
            status_code=400,
        )

    if len(new_password) < 8:
        return templates.TemplateResponse(
            request=request,
            name="settings.html",
            context={
                "creator": {
                    "slug": creator.slug,
                    "display_name": creator.display_name,
                    "bio": creator.bio,
                    "btc_address": creator.btc_address or "",
                    "xmr_address": creator.xmr_address or "",
                },
                "active": "settings",
                "error": "New password must be at least 8 characters.",
                "success": None,
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
