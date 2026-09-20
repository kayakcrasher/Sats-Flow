"""FastAPI application factory for the SatsFlow web frontend.

Run with:
    uvicorn satsflow.web.app:app --reload --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from satsflow.web.routes import creator, dashboard, landing

WEB_DIR = Path(__file__).parent
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def create_app() -> FastAPI:
    app = FastAPI(
        title="SatsFlow",
        description="Self-hosted Bitcoin and Monero donation platform.",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
    )

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    app.include_router(landing.router)
    app.include_router(creator.router)
    app.include_router(dashboard.router)

    return app


app = create_app()
