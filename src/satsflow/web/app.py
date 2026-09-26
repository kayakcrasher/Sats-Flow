"""FastAPI application factory for the SatsFlow web frontend."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from satsflow.core.payment_watcher import PaymentWatcher
from satsflow.storage.db import Database
from satsflow.storage.seed import seed_demo
from satsflow.web.routes import (
    auth,
    creator,
    dashboard,
    donate,
    explore,
    landing,
    live,
    price,
    settings,
)
from satsflow.web.templating import STATIC_DIR


def create_app() -> FastAPI:
    app = FastAPI(
        title="SatsFlow",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
    )

    db = Database()
    seed_demo(db)
    app.state.db = db
    app.state.watcher = PaymentWatcher(db)

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    app.include_router(landing.router)
    app.include_router(auth.router)
    app.include_router(creator.router)
    app.include_router(donate.router)
    app.include_router(dashboard.router)
    app.include_router(live.router)
    app.include_router(explore.router)
    app.include_router(settings.router)
    app.include_router(price.router)

    return app


app = create_app()
