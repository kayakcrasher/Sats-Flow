"""Helpers for auth-aware routes."""
from __future__ import annotations

from fastapi import Request

from satsflow.security.sessions import COOKIE_NAME
from satsflow.storage.db import Database
from satsflow.storage.models import Creator


def current_creator(request: Request) -> Creator | None:
    """Return the logged-in creator, or None if not authenticated."""
    db: Database = request.app.state.db
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    return db.get_session_creator(token)


def require_creator(request: Request) -> Creator:
    """Return the logged-in creator or raise 401."""
    from fastapi import HTTPException

    creator = current_creator(request)
    if creator is None:
        raise HTTPException(status_code=401, detail="Login required")
    return creator
