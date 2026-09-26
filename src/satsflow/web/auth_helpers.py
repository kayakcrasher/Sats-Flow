"""Helpers for auth-aware routes."""
from __future__ import annotations

from fastapi import Request

from satsflow.security.sessions import COOKIE_NAME
from satsflow.storage.db import Database
from satsflow.storage.models import User


def current_user(request: Request) -> User | None:
    """Return the logged-in user, or None if not authenticated."""
    db: Database = request.app.state.db
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    return db.get_session_user(token)


def require_user(request: Request) -> User:
    """Return the logged-in user or raise 401."""
    from fastapi import HTTPException

    user = current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Login required")
    return user
