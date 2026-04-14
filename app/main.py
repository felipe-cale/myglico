from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import desc, select

from app.api.routes import router
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.entities import AnalyticsRun
from app.services.semantic import load_graph


settings = get_settings()
APP_DIR = Path(__file__).resolve().parent
PROJECT_DIR = APP_DIR.parent

app = FastAPI(title=settings.app_name, debug=settings.debug)
app.include_router(router)
app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")
app.mount("/artifacts", StaticFiles(directory=str(PROJECT_DIR / "artifacts")), name="artifacts")


@app.on_event("startup")
def warm_semantic_cache() -> None:
    with SessionLocal() as db:
        latest_run = db.scalars(select(AnalyticsRun).order_by(desc(AnalyticsRun.started_at))).first()
        if latest_run and latest_run.semantic_ttl_path:
            load_graph(latest_run.semantic_ttl_path)
