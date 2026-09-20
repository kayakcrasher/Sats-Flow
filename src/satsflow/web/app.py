"""FastAPI application factory for the SatsFlow web frontend."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from satsflow.web.routes import creator, dashboard, landing
from satsflow.web.templating import STATIC_DIR

WEB_DIR_STATIC = STATIC_DIR


def create_app() -> FastAPI:
    app = FastAPI(title="SatsFlow", version="0.1.0", docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.include_router(landing.router)
    app.include_router(creator.router)
    app.include_router(dashboard.router)
    return app


app = create_app()
