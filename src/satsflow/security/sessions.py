"""Session token generation and cookie helpers.

Tokens are 32 random bytes, URL-safe base64 encoded (~43 chars).
They are stored in the database as opaque strings — never hashed —
because they are already high-entropy and short-lived.

Cookie policy:
  - httponly: JS can't read it (XSS mitigation)
  - samesite: "lax" — CSRF protection with normal navigation
  - secure: set True in production behind HTTPS
  - path: "/" — visible site-wide
"""

from __future__ import annotations

import secrets

COOKIE_NAME = "satsflow_session"
COOKIE_MAX_AGE = 30 * 24 * 3600  # 30 days, matches DB ttl


def new_token() -> str:
    """Generate a fresh session token."""
    return secrets.token_urlsafe(32)


def cookie_kwargs(secure: bool = False) -> dict:
    """Return kwargs for Response.set_cookie()."""
    return {
        "key": COOKIE_NAME,
        "httponly": True,
        "samesite": "lax",
        "secure": secure,
        "max_age": COOKIE_MAX_AGE,
        "path": "/",
    }
