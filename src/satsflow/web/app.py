"""FastAPI application factory for the SatsFlow web frontend."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from satsflow.storage.db import Database
from satsflow.storage.seed import seed_demo
from satsflow.web.routes import creator, dashboard, landing
from satsflow.web.templating import STATIC_DIR


def create_app() -> FastAPI:
    app = FastAPI(
        title="SatsFlow",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
    )

    # Storage: one Database instance for the process lifetime.
    # Routes access via request.app.state.db.
    db = Database()
    seed_demo(db)
    app.state.db = db

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    app.include_router(landing.router)
    app.include_router(creator.router)
    app.include_router(dashboard.router)

    return app


app = create_app()
