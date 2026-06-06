from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.core.config import get_settings
from app.services.clinical_pdf import preload_report_assets


settings = get_settings()
PROJECT_DIR = Path(__file__).resolve().parent.parent

app = FastAPI(title=settings.app_name, debug=settings.debug)
app.mount("/artifacts", StaticFiles(directory=str(PROJECT_DIR / "artifacts")), name="artifacts")
app.include_router(router)


@app.on_event("startup")
def warm_report_assets() -> None:
    preload_report_assets()
