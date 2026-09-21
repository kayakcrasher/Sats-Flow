"""Signup, login, logout routes."""
from __future__ import annotations

import re

from fastapi import APIRouter, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse

from satsflow.security.passwords import hash_password, verify_password
from satsflow.security.sessions import COOKIE_NAME, cookie_kwargs, new_token
from satsflow.storage.db import Database, DuplicateError, NotFoundError
from satsflow.web.templating import templates

router = APIRouter(prefix="/auth")

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,30}[a-z0-9]$")


def _flash(request: Request, message: str) -> None:
    """One-shot flash stored on the request state for the current response."""
    request.state.flash = message


@router.get("/signup", response_class=HTMLResponse)
async def signup_form(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="auth_signup.html",
        context={"active": "signup", "error": None},
    )


@router.post("/signup")
async def signup(
    request: Request,
    slug: str = Form(...),
    display_name: str = Form(...),
    bio: str = Form(""),
    password: str = Form(...),
    btc_address: str = Form(""),
    xmr_address: str = Form(""),
) -> Response:
    db: Database = request.app.state.db

    slug = slug.strip().lower()
    display_name = display_name.strip()

    if not SLUG_RE.match(slug):
        return templates.TemplateResponse(
            request=request,
            name="auth_signup.html",
            context={
                "active": "signup",
                "error": "Slug must be 3-32 chars, lowercase letters, digits, dash, underscore.",
            },
            status_code=400,
        )

    if len(password) < 8:
        return templates.TemplateResponse(
            request=request,
            name="auth_signup.html",
            context={"active": "signup", "error": "Password must be at least 8 characters."},
            status_code=400,
        )

    if not display_name:
        return templates.TemplateResponse(
            request=request,
            name="auth_signup.html",
            context={"active": "signup", "error": "Display name is required."},
            status_code=400,
        )

    try:
        creator = db.create_creator(
            slug=slug,
            display_name=display_name,
            bio=bio.strip(),
            btc_address=btc_address.strip() or None,
            xmr_address=xmr_address.strip() or None,
            password_hash=hash_password(password),
        )
    except DuplicateError:
        return templates.TemplateResponse(
            request=request,
            name="auth_signup.html",
            context={"active": "signup", "error": f"Slug '{slug}' is already taken."},
            status_code=400,
        )

    if creator.id is None:
        raise HTTPException(status_code=500, detail="creator id missing")

    token = new_token()
    db.create_session(creator.id, token)

    resp = RedirectResponse(url=f"/c/{creator.slug}", status_code=303)
    resp.set_cookie(value=token, **cookie_kwargs())
    return resp


@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="auth_login.html",
        context={"active": "login", "error": None},
    )


@router.post("/login")
async def login(
    request: Request,
    slug: str = Form(...),
    password: str = Form(...),
) -> Response:
    db: Database = request.app.state.db
    slug = slug.strip().lower()

    try:
        creator = db.get_creator_by_slug(slug)
    except NotFoundError:
        return templates.TemplateResponse(
            request=request,
            name="auth_login.html",
            context={"active": "login", "error": "Invalid slug or password."},
            status_code=400,
        )

    if not creator.password_hash or not verify_password(creator.password_hash, password):
        return templates.TemplateResponse(
            request=request,
            name="auth_login.html",
            context={"active": "login", "error": "Invalid slug or password."},
            status_code=400,
        )

    if creator.id is None:
        raise HTTPException(status_code=500, detail="creator id missing")

    token = new_token()
    db.create_session(creator.id, token)

    resp = RedirectResponse(url="/dashboard", status_code=303)
    resp.set_cookie(value=token, **cookie_kwargs())
    return resp


@router.post("/logout")
async def logout(request: Request) -> Response:
    db: Database = request.app.state.db
    token = request.cookies.get(COOKIE_NAME)
    if token:
        db.delete_session(token)

    resp = RedirectResponse(url="/", status_code=303)
    resp.delete_cookie(COOKIE_NAME, path="/")
    return resp
