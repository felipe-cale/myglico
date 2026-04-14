from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.reports import get_dashboard_context, get_patient_detail_context
from app.services.semantic import SAMPLE_QUERIES, execute_sparql


BASE_DIR = Path(__file__).resolve().parents[2]
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))
router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    context = get_dashboard_context(db)
    context["request"] = request
    return templates.TemplateResponse(request=request, name="index.html", context=context)


@router.get("/patients/{patient_id}", response_class=HTMLResponse)
def patient_detail(patient_id: int, request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    context = get_patient_detail_context(db, patient_id)
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


@router.get("/api/patients")
def api_patients(db: Session = Depends(get_db)) -> dict[str, object]:
    context = get_dashboard_context(db)
    return {"patients": context["patients"], "count": context["patient_count"]}


@router.get("/api/patients/{patient_id}")
def api_patient_detail(patient_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    context = get_patient_detail_context(db, patient_id)
    if context is None:
        raise HTTPException(status_code=404, detail="Patient not found.")
    return {
        "patient": {
            "id": context["patient"].id,
            "display_name": context["patient"].display_name,
            "source_file": context["patient"].source_file,
        },
        "summary": context["summary"],
        "daily_indicators": [
            {
                "date": indicator.indicator_date.isoformat(),
                "avg_glucose": indicator.avg_glucose,
                "pct_hypo": indicator.pct_hypo,
                "pct_in_range": indicator.pct_in_range,
                "pct_hyper": indicator.pct_hyper,
                "anomaly_flag": indicator.anomaly_flag,
                "cluster_label": indicator.cluster_label,
            }
            for indicator in context["indicators"]
        ],
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
