from __future__ import annotations

from pathlib import Path

import asyncio
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.notification_outbox import drain_notification_outbox
from app.services.clinical_pdf import preload_report_assets


settings = get_settings()
PROJECT_DIR = Path(__file__).resolve().parent.parent

app = FastAPI(title=settings.app_name, debug=settings.debug)

_artifacts_dir = PROJECT_DIR / "artifacts"
if _artifacts_dir.is_dir():
    app.mount("/artifacts", StaticFiles(directory=str(_artifacts_dir)), name="artifacts")

app.include_router(router)


logger = logging.getLogger(__name__)


@app.on_event("startup")
def warm_report_assets() -> None:
    preload_report_assets()


def _drain_outbox_once() -> None:
    with SessionLocal() as db:
        drain_notification_outbox(db)


async def _notification_dispatch_loop(interval_seconds: float) -> None:
    while True:
        try:
            await asyncio.to_thread(_drain_outbox_once)
        except Exception:
            # Rows keep their own retry state; the next tick picks them up.
            logger.exception("Notification outbox drain failed")
        await asyncio.sleep(interval_seconds)


@app.on_event("startup")
async def start_notification_dispatcher() -> None:
    app.state.notification_dispatcher = None
    if settings.notification_dispatcher == "loop":
        app.state.notification_dispatcher = asyncio.create_task(
            _notification_dispatch_loop(settings.notification_dispatch_interval_seconds)
        )


@app.on_event("shutdown")
async def stop_notification_dispatcher() -> None:
    task = getattr(app.state, "notification_dispatcher", None)
    if task is not None:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


@app.middleware("http")
async def prevent_private_api_caching(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path.startswith((
        "/api/auth/", "/api/patients", "/api/doctors/search",
        "/api/investigations", "/api/notifications", "/api/doctor-links",
    )):
        response.headers["Cache-Control"] = "no-store, private"
    return response


@app.exception_handler(RequestValidationError)
async def scrub_validation_inputs(request: Request, exc: RequestValidationError) -> JSONResponse:
    # FastAPI's default validation payload can echo submitted values. Keep
    # passwords and other personal fields out of error responses.
    return JSONResponse(status_code=422, content={"detail": "Invalid request."})
