from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.entities import Patient
from app.services.clinical_pdf import build_patient_report_pdf, patient_report_filename
from app.services.manual_entry import create_manual_glucose_record, create_patient
from app.services.reports import get_dashboard_summary, get_paginated_patients, get_patient_detail_context, get_patient_report_context


router = APIRouter()


class PatientCreatePayload(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    email: str | None = Field(default=None, max_length=254)


class ManualGlucoseRecordPayload(BaseModel):
    measured_at: datetime
    glucose_mg_dl: float = Field(gt=0, le=1000)
    context_label: str | None = Field(default=None, max_length=80)
    notes: str | None = None
    actor_user_id: str | None = Field(default=None, max_length=36)


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
    signal: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return get_paginated_patients(db, page=page, page_size=page_size, query=q, signal=signal)


@router.post("/api/patients", status_code=201)
def api_create_patient(payload: PatientCreatePayload, db: Session = Depends(get_db)) -> dict[str, object]:
    patient = create_patient(db, name=payload.name.strip(), email=payload.email)
    return {
        "patient": {
            "id": patient.id,
            "name": patient.name,
            "display_name": patient.display_name,
            "email": patient.email,
            "created_at": patient.created_at.isoformat(),
            "updated_at": patient.updated_at.isoformat(),
        }
    }


@router.get("/api/patients/{patient_id}")
def api_patient_detail(
    patient_id: str,
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
            "name": context["patient"].name,
            "email": context["patient"].email,
            "source_file": context["patient"].source_file,
        },
        "filters": context["filters"],
        "analytics_status": context["analytics_status"],
        "summary": context["summary"],
        "daily_indicators": context["daily_indicators_json"],
        "glucose_events": context["glucose_events_json"],
        "recent_events": context["recent_events_json"],
        "hourly_lows": context["hourly_lows"],
        "hourly_highs_250": context["hourly_highs_250"],
    }


SUPPORTED_REPORT_LANGS = {"pt-BR", "en-US", "es"}


@router.get("/api/patients/{patient_id}/report.pdf")
def api_patient_report_pdf(
    patient_id: str,
    start_date: date = Query(...),
    end_date: date = Query(...),
    lang: str = Query("pt-BR"),
    db: Session = Depends(get_db),
) -> Response:
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must be before or equal to end_date.")

    if lang not in SUPPORTED_REPORT_LANGS:
        lang = "pt-BR"

    context = get_patient_report_context(db, patient_id, start_date=start_date, end_date=end_date)
    if context is None:
        raise HTTPException(status_code=404, detail="Patient not found.")

    pdf = build_patient_report_pdf(context, lang=lang)
    filename = patient_report_filename(context, lang=lang)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/api/patients/{patient_id}/glucose-records", status_code=201)
def api_create_manual_glucose_record(
    patient_id: str,
    payload: ManualGlucoseRecordPayload,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found.")
    record = create_manual_glucose_record(
        db,
        patient=patient,
        measured_at=payload.measured_at,
        glucose_mg_dl=payload.glucose_mg_dl,
        context_label=payload.context_label,
        notes=payload.notes,
        actor_user_id=payload.actor_user_id,
    )
    return {
        "glucose_record": {
            "id": record.id,
            "patient_id": record.patient_id,
            "measured_at": record.measured_at.isoformat(),
            "glucose_mg_dl": record.glucose_mg_dl,
            "context_label": record.context_label,
            "analytics_status": "stale",
        }
    }
