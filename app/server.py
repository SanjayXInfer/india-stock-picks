"""Local FastAPI server: serves the dashboard, its data and the Refresh endpoint. Binds to 127.0.0.1 only."""
from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config, db
from .aggregate import build_payload
from .pipeline import is_running
from .publish import scrape_and_publish
from .scheduler import start_scheduler

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    sched = start_scheduler()
    yield
    sched.shutdown(wait=False)


app = FastAPI(title="India Stock Reco Dashboard", lifespan=lifespan, docs_url=None, redoc_url=None)


@app.get("/data.json")
def data():
    return JSONResponse(build_payload(mode="local"), headers={"Cache-Control": "no-store"})


@app.get("/api/status")
def status():
    with db.session() as conn:
        return {"running": is_running(), "last_run": db.get_meta(conn, "last_run")}


@app.post("/api/refresh")
def refresh():
    if is_running():
        return {"status": "already running"}
    threading.Thread(target=scrape_and_publish, daemon=True, name="manual-refresh").start()
    return {"status": "started"}


# Static frontend last, so the routes above take precedence.
app.mount("/", StaticFiles(directory=config.WEB_DIR, html=True), name="web")
