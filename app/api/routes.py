from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.reports import get_dashboard_context, get_dashboard_summary, get_paginated_patients, get_patient_detail_context
from app.services.semantic import SAMPLE_QUERIES, execute_sparql


BASE_DIR = Path(__file__).resolve().parents[2]
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))
REACT_DIST_DIR = BASE_DIR / "frontend-react" / "client-build"
router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    context = get_dashboard_context(db)
    context["request"] = request
    return templates.TemplateResponse(request=request, name="index.html", context=context)


@router.get("/patients/{patient_id}", response_class=HTMLResponse)
def patient_detail(
    patient_id: int,
    request: Request,
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    context = get_patient_detail_context(db, patient_id, start_date=start_date, end_date=end_date)
    if context is None:
        raise HTTPException(status_code=404, detail="Patient not found.")
    context["request"] = request
    return templates.TemplateResponse(request=request, name="patients/detail.html", context=context)


@router.get("/semantic", response_class=HTMLResponse)
def semantic_view(
    request: Request,
    name: str | None = Query(default=None),
    q: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    dashboard = get_dashboard_context(db)
    latest_run = dashboard["latest_run"]
    query_name = name or "high_risk_days"
    query_text = SAMPLE_QUERIES.get(query_name, q or SAMPLE_QUERIES["high_risk_days"])
    results = []
    if (name or q) and latest_run and latest_run.semantic_ttl_path:
        results = execute_sparql(latest_run.semantic_ttl_path, query_text, limit=100)
    context = {
        "request": request,
        "sample_queries": SAMPLE_QUERIES,
        "query_name": query_name,
        "query_text": query_text,
        "results": results,
    }
    return templates.TemplateResponse(request=request, name="semantic.html", context=context)


@router.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/api/dashboard")
def api_dashboard(db: Session = Depends(get_db)) -> dict[str, object]:
    summary = get_dashboard_summary(db)
    return {
        "metrics": {
            "patient_count": summary["patient_count"],
            "normalized_count": summary["normalized_count"],
            "indicator_count": summary["indicator_count"],
            "issue_count": summary["issue_count"],
        },
        "links": {
            "latest_batch": summary["latest_batch_links"],
            "latest_run": summary["latest_run_links"],
        },
    }


@router.get("/api/patients")
def api_patients(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=12, ge=1, le=50),
    q: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return get_paginated_patients(db, page=page, page_size=page_size, query=q)


@router.get("/api/patients/{patient_id}")
def api_patient_detail(
    patient_id: int,
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    context = get_patient_detail_context(db, patient_id, start_date=start_date, end_date=end_date)
    if context is None:
        raise HTTPException(status_code=404, detail="Patient not found.")
    return {
        "patient": {
            "id": context["patient"].id,
            "display_name": context["patient"].display_name,
            "source_file": context["patient"].source_file,
        },
        "filters": context["filters"],
        "summary": context["summary"],
        "daily_indicators": context["daily_indicators_json"],
        "glucose_events": context["glucose_events_json"],
        "recent_events": context["recent_events_json"],
        "hourly_lows": context["hourly_lows"],
        "hourly_highs_250": context["hourly_highs_250"],
    }


@router.get("/api/semantic/query")
def api_semantic_query(
    name: str = Query(default="high_risk_days"),
    q: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> JSONResponse:
    context = get_dashboard_context(db)
    latest_run = context["latest_run"]
    if latest_run is None or not latest_run.semantic_ttl_path:
        raise HTTPException(status_code=404, detail="No semantic graph available yet.")
    query_text = SAMPLE_QUERIES.get(name, q or SAMPLE_QUERIES["high_risk_days"])
    results = execute_sparql(latest_run.semantic_ttl_path, query_text, limit=100)
    return JSONResponse({"query": query_text, "results": results})


@router.get("/api/semantic/queries")
def api_semantic_queries() -> dict[str, object]:
    return {"queries": SAMPLE_QUERIES}


@router.get("/react", response_class=HTMLResponse, include_in_schema=False)
@router.get("/react/{full_path:path}", response_class=HTMLResponse, include_in_schema=False)
def react_preview(full_path: str = "") -> FileResponse:
    requested = (REACT_DIST_DIR / full_path).resolve() if full_path else REACT_DIST_DIR / "index.html"
    if full_path and requested.exists() and requested.is_file() and REACT_DIST_DIR in requested.parents:
        return FileResponse(requested)

    index_file = REACT_DIST_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)

    raise HTTPException(status_code=503, detail="React preview not built yet.")
