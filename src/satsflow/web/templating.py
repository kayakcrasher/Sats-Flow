"""Shared Jinja2Templates instance."""
from __future__ import annotations

from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates

from satsflow.security.sessions import COOKIE_NAME

WEB_DIR = Path(__file__).parent
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _session_user(request: Request):
    """Look up the logged-in user for use in every template."""
    try:
        db = request.app.state.db
    except AttributeError:
        return None
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    return db.get_session_user(token)


templates.env.globals["session_user"] = _session_user
