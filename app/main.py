from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.core.config import get_settings
from app.services.clinical_pdf import preload_report_assets


settings = get_settings()
PROJECT_DIR = Path(__file__).resolve().parent.parent

app = FastAPI(title=settings.app_name, debug=settings.debug)

_artifacts_dir = PROJECT_DIR / "artifacts"
if _artifacts_dir.is_dir():
    app.mount("/artifacts", StaticFiles(directory=str(_artifacts_dir)), name="artifacts")

app.include_router(router)


@app.on_event("startup")
def warm_report_assets() -> None:
    preload_report_assets()


@app.middleware("http")
async def prevent_private_api_caching(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith(("/api/auth/", "/api/patients", "/api/doctors/search")):
        response.headers["Cache-Control"] = "no-store, private"
    return response


@app.exception_handler(RequestValidationError)
async def scrub_validation_inputs(request: Request, exc: RequestValidationError) -> JSONResponse:
    # FastAPI's default validation payload can echo submitted values. Keep
    # passwords and other personal fields out of error responses.
    return JSONResponse(status_code=422, content={"detail": "Invalid request."})
