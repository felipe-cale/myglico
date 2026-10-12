from __future__ import annotations

from datetime import date, datetime
from enum import IntEnum
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.crypto import crm_uf_lookup, decrypt_field
from app.core.patient_time import local_date_utc_bounds, patient_local_datetime
from app.core.security import (
    SESSION_COOKIE_NAME,
    SessionPrincipal,
    clear_session_cookie,
    require_session,
    resolve_session,
    set_session_cookie,
)
from app.core.rate_limit import consume as consume_rate_limit
from app.db.session import get_db
from app.models.entities import AnalysisRun, DataQualityIssue, DailyIndicator, Doctor, GlucoseRecord, InvestigationMessage, Notification, Patient, PatientDoctorLink, ProvenanceEvent
from app.models.entities import Investigation
from app.services.clinical_pdf import build_patient_report_pdf, patient_report_filename
from app.services.auth_service import (
    AuthConflict,
    InvalidCredentials,
    doctor_payload,
    login_account,
    patient_payload,
    register_account,
    revoke_session,
)
from app.services.doctor_links import (
    LinkConflict, LinkNotFound, list_links, notification_list, request_link, transition_link,
)
from app.services.investigations import (
    InvestigationConflict, InvestigationNotFound, advance_read_position,
    append_message, close_investigation, defer_prompt, defer_prompt_batch, investigation_detail,
    investigation_list, open_investigation, unread_message_count,
)
from app.services.manual_entry import create_manual_glucose_record
from app.services.reports import (
    get_latest_patient_analytics_run, get_paginated_patients,
    get_patient_detail_context, get_patient_report_context,
)


router = APIRouter()


class PageSize(IntEnum):
    TEN = 10
    TWENTY_FIVE = 25
    FIFTY = 50


def _enforce_rate_limit(request: Request, scope: str, identity: str) -> None:
    ip_address = request.client.host if request.client else "unknown"
    allowed, retry_after = consume_rate_limit(scope, ip_address, identity)
    if not allowed:
        raise HTTPException(
            status_code=429, detail="Too many requests.",
            headers={"Retry-After": str(retry_after)},
        )


class PatientCreatePayload(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    email: str | None = Field(default=None, max_length=254)


class AuthRegisterPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["patient", "doctor"]
    email: str = Field(min_length=3, max_length=254)
    password: SecretStr = Field(min_length=8, max_length=256)
    password_confirmation: SecretStr = Field(min_length=8, max_length=256)
    display_name: str = Field(min_length=1, max_length=160)
    crm: str | None = Field(default=None, max_length=40)
    uf: str | None = Field(default=None, min_length=2, max_length=2)
    privacy_notice_accepted: bool = False

    @field_validator("email")
    @classmethod
    def validate_email_shape(cls, value: str) -> str:
        value = value.strip()
        local, separator, domain = value.rpartition("@")
        if (
            not separator
            or not local
            or not domain
            or "." not in domain
            or domain.startswith(".")
            or domain.endswith(".")
        ):
            raise ValueError("Invalid email address.")
        return value

    @model_validator(mode="after")
    def validate_password_confirmation(self) -> "AuthRegisterPayload":
        if self.password.get_secret_value() != self.password_confirmation.get_secret_value():
            raise ValueError("Password confirmation does not match.")
        if self.role == "doctor":
            if not self.crm or not self.crm.strip() or not self.uf or not self.uf.strip():
                raise ValueError("Doctor registration requires CRM and UF.")
        if not self.privacy_notice_accepted:
            raise ValueError("Registration requires privacy_notice_accepted=true.")
        return self


class AuthLoginPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=1, max_length=254)
    password: SecretStr = Field(min_length=1, max_length=256)


class AtypicalPromptDeferBatchPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    indicator_ids: list[str] = Field(min_length=1, max_length=100)


class DoctorLinkRequestPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    doctor_short_id: str = Field(min_length=6, max_length=6)


class DoctorLinkVersionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=1)
    reason: str | None = Field(default=None, max_length=1000)


class InvestigationOpenPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    doctor_id: str | None = Field(default=None, min_length=36, max_length=36)
    patient_id: str | None = Field(default=None, min_length=36, max_length=36)
    atypical_day_event_id: str | None = Field(default=None, min_length=36, max_length=36)
    atypical_day_event_ids: list[str] = Field(default_factory=list, max_length=100)
    title: str = Field(min_length=1, max_length=180)
    initial_message: str = Field(min_length=1, max_length=10000)


class InvestigationMessagePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1, max_length=10000)
    idempotency_key: str | None = Field(default=None, max_length=128)


class InvestigationReadPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    up_to_sequence: int = Field(ge=0)


class InvestigationClosePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    observation: str | None = Field(default=None, max_length=2000)
    version: int = Field(ge=1)


class ManualGlucoseRecordPayload(BaseModel):
    measured_at: datetime
    glucose_mg_dl: float = Field(gt=0, le=1000)
    context_label: str | None = Field(default=None, max_length=80)
    notes: str | None = None
    actor_user_id: str | None = Field(default=None, max_length=36)


@router.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


def _identity_session_response(
    patient: Patient | None,
    doctor: Doctor | None,
) -> dict[str, object]:
    result: dict[str, object] = {"authenticated": True}
    if patient is not None:
        result["patient"] = patient_payload(patient)
    if doctor is not None:
        result["doctor"] = doctor_payload(doctor)
    return result


@router.post("/api/auth/register", status_code=201)
def api_auth_register(
    payload: AuthRegisterPayload,
    response: Response,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    try:
        identity = register_account(
            db,
            role=payload.role,
            email=payload.email,
            password=payload.password.get_secret_value(),
            display_name=payload.display_name,
            crm=payload.crm,
            uf=payload.uf,
            privacy_notice_accepted=payload.privacy_notice_accepted,
        )
    except AuthConflict as exc:
        raise HTTPException(status_code=409, detail="Account could not be created.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid registration details.") from exc

    set_session_cookie(response, identity.session_token, identity.session.expires_at)
    roles = []
    if identity.patient is not None:
        roles.append("patient")
    if identity.doctor is not None:
        roles.append("doctor")
    result: dict[str, object] = {"account": {"roles": roles}}
    if identity.patient is not None:
        result["patient"] = patient_payload(identity.patient)
    if identity.doctor is not None:
        result["doctor"] = doctor_payload(identity.doctor)
    return result


@router.post("/api/auth/login")
def api_auth_login(
    payload: AuthLoginPayload,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    _enforce_rate_limit(request, "login", payload.email.strip().lower())
    try:
        identity = login_account(db, email=payload.email, password=payload.password.get_secret_value())
    except InvalidCredentials as exc:
        raise HTTPException(status_code=401, detail="Invalid email or password.") from exc
    set_session_cookie(response, identity.session_token, identity.session.expires_at)
    return _identity_session_response(identity.patient, identity.doctor)


@router.post("/api/auth/logout", status_code=204)
def api_auth_logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> Response:
    # The route is intentionally idempotent; even an absent/expired session
    # receives a cleared cookie and a 204 response.
    revoke_session(db, request.cookies.get(SESSION_COOKIE_NAME))
    clear_session_cookie(response)
    response.status_code = 204
    return response


@router.get("/api/auth/session")
def api_auth_session(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    principal = resolve_session(request, db)
    if principal is None:
        clear_session_cookie(response)
        return {"authenticated": False}
    return _identity_session_response(principal.patient, principal.doctor)


@router.get("/api/doctors/search")
def api_doctor_search(
    request: Request,
    short_id: str | None = Query(default=None, min_length=6, max_length=6),
    crm: str | None = Query(default=None, min_length=1, max_length=40),
    uf: str | None = Query(default=None, min_length=2, max_length=2),
    principal: SessionPrincipal = Depends(require_session),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    _enforce_rate_limit(request, "doctor_search", principal.account.id)
    if principal.patient is None:
        raise HTTPException(status_code=403, detail="Patient access required.")
    if short_id:
        if crm is not None or uf is not None:
            raise HTTPException(status_code=400, detail="Choose one doctor search method.")
        doctor = db.scalar(select(Doctor).where(Doctor.short_id == short_id.strip().upper()))
    elif crm is not None and uf is not None:
        lookup = crm_uf_lookup(crm, uf)
        doctor = db.scalar(select(Doctor).where(Doctor.crm_uf_lookup == lookup))
    else:
        raise HTTPException(status_code=400, detail="Provide SHORTID or both CRM and UF.")

    if doctor is None:
        return {"doctor": None}
    doctor_info = doctor_payload(doctor)
    link = None
    if principal.patient is not None:
        link = db.scalar(select(PatientDoctorLink).where(
            PatientDoctorLink.patient_id == principal.patient.id,
            PatientDoctorLink.doctor_id == doctor.id,
            PatientDoctorLink.status.in_(("PENDING", "ACTIVE")),
        ))
    return {
        "doctor": {
            "short_id": doctor_info["short_id"],
            "name": doctor_info["name"],
            "crm": doctor_info["crm"],
            "uf": doctor_info["uf"],
            "is_demo": doctor_info["is_demo"],
            "declared_verified": doctor_info["declared_verified"],
            "link_status": link.status.lower() if link is not None else "none",
        }
    }


def _doctor_link_payload(link: PatientDoctorLink, *, context_role: str) -> dict[str, object]:
    doctor = link.doctor
    doctor_info = doctor_payload(doctor)
    payload: dict[str, object] = {
        "id": link.id,
        "patient_id": link.patient_id,
        "doctor_id": link.doctor_id,
        "status": link.status.lower(),
        "version": link.version,
        "requested_at": link.requested_at.isoformat(),
        "decided_at": link.decided_at.isoformat() if link.decided_at else None,
        "revoked_at": link.revoked_at.isoformat() if link.revoked_at else None,
        "doctor": {
            "short_id": doctor_info["short_id"], "name": doctor_info["name"],
            "crm": doctor_info["crm"], "uf": doctor_info["uf"],
            "is_demo": doctor_info["is_demo"], "declared_verified": doctor_info["declared_verified"],
        },
    }
    if context_role == "doctor":
        payload["patient"] = {
            "short_id": link.patient.short_id,
            "display_name": link.patient.display_name,
        }
    return payload


@router.post("/api/doctor-links", status_code=201)
def api_doctor_link_request(
    payload: DoctorLinkRequestPayload,
    request: Request,
    response: Response,
    principal: SessionPrincipal = Depends(require_session),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    _enforce_rate_limit(request, "doctor_link_request", principal.account.id)
    if principal.patient is None:
        raise HTTPException(status_code=403, detail="Patient access required.")
    try:
        link, created = request_link(db, principal, payload.doctor_short_id)
    except LinkNotFound as exc:
        raise HTTPException(status_code=404, detail="Doctor not found.") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="Cannot request an association with your own doctor profile.") from exc
    except LinkConflict as exc:
        raise HTTPException(status_code=409, detail="An open association already exists.") from exc
    if not created:
        response.status_code = 200
    return {"link": _doctor_link_payload(link, context_role="patient")}


@router.get("/api/doctor-links")
def api_doctor_links(
    status: str | None = Query(default=None),
    link_id: str | None = Query(default=None, max_length=36),
    patient_id: str | None = Query(default=None, max_length=36),
    page: int = Query(default=1, ge=1),
    page_size: PageSize = Query(default=PageSize.TEN),
    principal: SessionPrincipal = Depends(require_session),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    context = "doctor" if principal.doctor is not None and principal.patient is None else "patient"
    if status and status.upper() not in {"PENDING", "ACTIVE", "REVOKED", "REJECTED", "CANCELLED"}:
        raise HTTPException(status_code=400, detail="Invalid association status.")
    links, total, current_page = list_links(
        db, principal, status=status, page=page, page_size=page_size, link_id=link_id,
        patient_id=patient_id,
    )
    return {
        "links": [_doctor_link_payload(link, context_role=context) for link in links],
        "pagination": {
            "page": current_page, "page_size": page_size, "total": total,
            "pages": max(1, (total + page_size - 1) // page_size),
        },
    }


def _mutate_link(
    link_id: str, action: str, payload: DoctorLinkVersionPayload,
    principal: SessionPrincipal, db: Session,
) -> dict[str, object]:
    try:
        link = transition_link(db, link_id, principal, action, payload.version, payload.reason)
    except LinkNotFound as exc:
        raise HTTPException(status_code=404, detail="Association not found.") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="Not authorized for this association action.") from exc
    except LinkConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    context = "doctor" if principal.doctor is not None and principal.patient is None else "patient"
    return {"link": _doctor_link_payload(link, context_role=context)}


@router.post("/api/doctor-links/{link_id}/confirm")
def api_doctor_link_confirm(
    link_id: str, payload: DoctorLinkVersionPayload,
    principal: SessionPrincipal = Depends(require_session), db: Session = Depends(get_db),
) -> dict[str, object]:
    return _mutate_link(link_id, "confirm", payload, principal, db)


@router.post("/api/doctor-links/{link_id}/reject")
def api_doctor_link_reject(
    link_id: str, payload: DoctorLinkVersionPayload,
    principal: SessionPrincipal = Depends(require_session), db: Session = Depends(get_db),
) -> dict[str, object]:
    return _mutate_link(link_id, "reject", payload, principal, db)


@router.post("/api/doctor-links/{link_id}/cancel")
def api_doctor_link_cancel(
    link_id: str, payload: DoctorLinkVersionPayload,
    principal: SessionPrincipal = Depends(require_session), db: Session = Depends(get_db),
) -> dict[str, object]:
    return _mutate_link(link_id, "cancel", payload, principal, db)


@router.post("/api/doctor-links/{link_id}/revoke")
def api_doctor_link_revoke(
    link_id: str, payload: DoctorLinkVersionPayload,
    principal: SessionPrincipal = Depends(require_session), db: Session = Depends(get_db),
) -> dict[str, object]:
    return _mutate_link(link_id, "revoke", payload, principal, db)


@router.get("/api/notifications")
def api_notifications(
    unread_only: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    page_size: PageSize = Query(default=PageSize.TEN),
    principal: SessionPrincipal = Depends(require_session), db: Session = Depends(get_db),
) -> dict[str, object]:
    notifications, unread_count, total, current_page = notification_list(
        db, principal.account.id, unread_only, page=page, page_size=page_size,
    )
    return {"notifications": [{
        "id": item.id, "notification_type": item.notification_type,
        "payload": item.payload, "causation_event_id": item.causation_event_id,
        "read_at": item.read_at.isoformat() if item.read_at else None,
        "created_at": item.created_at.isoformat(),
    } for item in notifications], "unread_count": unread_count, "pagination": {
        "page": current_page, "page_size": page_size, "total": total,
        "pages": max(1, (total + page_size - 1) // page_size),
    }}


@router.get("/api/notifications/unread-summary")
def api_notification_unread_summary(
    principal: SessionPrincipal = Depends(require_session), db: Session = Depends(get_db),
) -> dict[str, int]:
    _notifications, notification_count, _total, _page = notification_list(db, principal.account.id, unread_only=True)
    return {"notifications_unread": notification_count,
            "messages_unread": unread_message_count(db, principal)}


@router.post("/api/notifications/{notification_id}/read")
def api_notification_read(
    notification_id: str,
    principal: SessionPrincipal = Depends(require_session), db: Session = Depends(get_db),
) -> dict[str, object]:
    item = db.scalar(select(Notification).where(
        Notification.id == notification_id,
        Notification.recipient_user_account_id == principal.account.id,
    ))
    if item is None:
        raise HTTPException(status_code=404, detail="Notification not found.")
    if item.read_at is None:
        item.read_at = datetime.utcnow()
        db.add(ProvenanceEvent(
            activity_type="NotificationRead", entity_type="notification", entity_id=item.id,
            actor_user_id=principal.account.id, source_type="user", source_id=item.id,
            occurred_at=datetime.utcnow(), prov_json={"activity": "NotificationRead"},
            metadata_json={"recipient_user_account_id": principal.account.id},
        ))
        db.commit()
    return {"notification": {"id": item.id, "read_at": item.read_at.isoformat()}}


def _investigation_summary(db: Session, item, context_role: str) -> dict[str, object]:
    counterpart: dict[str, object]
    if context_role == "PATIENT":
        doctor = db.get(Doctor, item.doctor_id)
        doctor_info = doctor_payload(doctor) if doctor else {}
        counterpart = {"role": "doctor", "id": item.doctor_id,
                       "short_id": doctor_info.get("short_id"), "name": doctor_info.get("name")}
    else:
        patient = db.get(Patient, item.patient_id)
        counterpart = {"role": "patient", "id": item.patient_id,
                       "short_id": patient.short_id if patient else None,
                       "display_name": patient.display_name if patient else None}
    title = decrypt_field(item.title_encrypted, table="investigations", column="title", record_id=item.id)
    origins = []
    origin_ids = [row.daily_indicator_id for row in item.atypical_days]
    if not origin_ids and item.atypical_day_event_id:
        origin_ids = [item.atypical_day_event_id]
    for origin_id in origin_ids:
        historical_indicator = db.get(DailyIndicator, origin_id)
        if historical_indicator is not None and historical_indicator.patient_id == item.patient_id:
            latest_run = get_latest_patient_analytics_run(db, item.patient_id)
            current_flag = False
            if latest_run is not None:
                current_flag = db.scalar(select(DailyIndicator.id).where(
                    DailyIndicator.analysis_run_id == latest_run.id,
                    DailyIndicator.patient_id == item.patient_id,
                    DailyIndicator.indicator_date == historical_indicator.indicator_date,
                    DailyIndicator.anomaly_flag.is_(True),
                ).limit(1)) is not None
            origins.append({
                "indicator_id": historical_indicator.id,
                "date": historical_indicator.indicator_date.isoformat(),
                "analysis_run_id": historical_indicator.analysis_run_id,
                "is_current_classification": current_flag,
            })
    origin = origins[0] if origins else None
    return {
        "id": item.id, "patient_id": item.patient_id, "doctor_id": item.doctor_id,
        "association_id": item.association_id, "atypical_day_event_id": item.atypical_day_event_id,
        "origin": origin, "origins": origins,
        "title": title, "status": item.status.lower(), "awaiting_role": item.awaiting_role.lower() if item.awaiting_role else None,
        "opened_by_role": item.opened_by_role.lower(), "opened_by_domain_id": item.opened_by_domain_id,
        "opened_at": item.opened_at.isoformat(), "closed_at": item.closed_at.isoformat() if item.closed_at else None,
        "closed_by": item.closed_by, "closed_reason": item.closed_reason, "version": item.version,
        "counterpart": counterpart,
    }


@router.post("/api/investigations", status_code=201)
def api_investigation_open(
    payload: InvestigationOpenPayload,
    principal: SessionPrincipal = Depends(require_session), db: Session = Depends(get_db),
) -> dict[str, object]:
    try:
        item = open_investigation(
            db, principal, doctor_id=payload.doctor_id, patient_id=payload.patient_id,
            atypical_day_event_id=payload.atypical_day_event_id,
            atypical_day_event_ids=payload.atypical_day_event_ids,
            title=payload.title, initial_message=payload.initial_message,
        )
    except InvestigationNotFound as exc:
        raise HTTPException(status_code=404, detail="Authorized association or event not found.") from exc
    except InvestigationConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    role = "PATIENT" if principal.patient is not None else "DOCTOR"
    return {"investigation": _investigation_summary(db, item, role)}


@router.get("/api/investigations")
def api_investigation_list(
    status: str | None = Query(default=None),
    counterpart_id: str | None = Query(default=None, max_length=36),
    page: int = Query(default=1, ge=1),
    page_size: PageSize = Query(default=PageSize.TEN),
    principal: SessionPrincipal = Depends(require_session), db: Session = Depends(get_db),
) -> dict[str, object]:
    role = "PATIENT" if principal.patient is not None else "DOCTOR"
    try:
        items, total, current_page = investigation_list(
            db, principal, status=status, counterpart_id=counterpart_id,
            page=page, page_size=page_size,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "investigations": [_investigation_summary(db, item, role) for item in items],
        "pagination": {
            "page": current_page, "page_size": page_size, "total": total,
            "pages": max(1, (total + page_size - 1) // page_size),
        },
    }


@router.get("/api/investigations/{investigation_id}")
def api_investigation_detail(
    investigation_id: str,
    page: int = Query(default=1, ge=1), page_size: int = Query(default=50, ge=1, le=100),
    principal: SessionPrincipal = Depends(require_session), db: Session = Depends(get_db),
) -> dict[str, object]:
    try:
        item, messages, total, role, unread_count = investigation_detail(
            db, investigation_id, principal, page=page, page_size=page_size,
        )
    except InvestigationNotFound as exc:
        raise HTTPException(status_code=404, detail="Investigation not found.") from exc
    except InvestigationConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "investigation": _investigation_summary(db, item, role),
        "messages": [{
            "id": message.id, "sequence": message.sequence,
            "author_role": message.author_role.lower(), "author_domain_id": message.author_domain_id,
            "content": decrypt_field(message.content_encrypted, table="investigation_messages", column="content", record_id=message.id),
            "created_at": message.created_at.isoformat(),
        } for message in messages],
        "pagination": {"page": page, "page_size": page_size, "total": total},
        "unread_count": unread_count,
    }


@router.post("/api/investigations/{investigation_id}/messages", status_code=201)
def api_investigation_message(
    investigation_id: str, payload: InvestigationMessagePayload,
    principal: SessionPrincipal = Depends(require_session), db: Session = Depends(get_db),
) -> dict[str, object]:
    try:
        message = append_message(db, investigation_id, principal, payload.content, payload.idempotency_key)
    except InvestigationNotFound as exc:
        raise HTTPException(status_code=404, detail="Investigation not found.") from exc
    except InvestigationConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"message": {
        "id": message.id, "sequence": message.sequence, "author_role": message.author_role.lower(),
        "author_domain_id": message.author_domain_id,
        "content": decrypt_field(message.content_encrypted, table="investigation_messages", column="content", record_id=message.id),
        "created_at": message.created_at.isoformat(),
    }}


@router.post("/api/investigations/{investigation_id}/read")
def api_investigation_read(
    investigation_id: str, payload: InvestigationReadPayload,
    principal: SessionPrincipal = Depends(require_session), db: Session = Depends(get_db),
) -> dict[str, object]:
    try:
        sequence = advance_read_position(db, investigation_id, principal, payload.up_to_sequence)
    except InvestigationNotFound as exc:
        raise HTTPException(status_code=404, detail="Investigation not found.") from exc
    except InvestigationConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"investigation_id": investigation_id, "last_read_sequence": sequence}


@router.post("/api/investigations/{investigation_id}/close")
def api_investigation_close(
    investigation_id: str, payload: InvestigationClosePayload,
    principal: SessionPrincipal = Depends(require_session), db: Session = Depends(get_db),
) -> dict[str, object]:
    try:
        item = close_investigation(
            db, investigation_id, principal, expected_version=payload.version,
            observation=payload.observation,
        )
    except InvestigationNotFound as exc:
        raise HTTPException(status_code=404, detail="Investigation not found.") from exc
    except InvestigationConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    role = "PATIENT" if principal.patient is not None else "DOCTOR"
    return {"investigation": _investigation_summary(db, item, role)}


@router.get("/api/patients/{patient_id}/atypical-day-prompts")
def api_atypical_day_prompts(
    patient_id: str, page: int = Query(default=1, ge=1),
    page_size: PageSize = Query(default=PageSize.TEN),
    indicator_id: str | None = Query(default=None, max_length=36),
    principal: SessionPrincipal = Depends(require_session), db: Session = Depends(get_db),
) -> dict[str, object]:
    if principal.patient is None or principal.patient.id != patient_id:
        raise HTTPException(status_code=404, detail="Patient not found.")
    from app.models.entities import AtypicalDayPrompt

    query = select(AtypicalDayPrompt).where(
        AtypicalDayPrompt.patient_id == patient_id,
        AtypicalDayPrompt.status == "CREATED",
    )
    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
    pages = max(1, (total + page_size - 1) // page_size)
    current_page = min(page, pages)
    if indicator_id:
        target = db.scalar(select(AtypicalDayPrompt).where(
            AtypicalDayPrompt.patient_id == patient_id,
            AtypicalDayPrompt.status == "CREATED",
            AtypicalDayPrompt.daily_indicator_id == indicator_id,
        ))
        if target:
            preceding = db.scalar(select(func.count(AtypicalDayPrompt.id)).where(
                AtypicalDayPrompt.patient_id == patient_id,
                AtypicalDayPrompt.status == "CREATED",
                (AtypicalDayPrompt.indicator_date > target.indicator_date)
                | ((AtypicalDayPrompt.indicator_date == target.indicator_date) & (AtypicalDayPrompt.id < target.id)),
            )) or 0
            current_page = preceding // page_size + 1
    prompts = list(db.scalars(
        query.order_by(AtypicalDayPrompt.indicator_date.desc(), AtypicalDayPrompt.id)
        .offset((current_page - 1) * page_size).limit(page_size)
    ))
    ordered = list(reversed(prompts))
    dates = [item.indicator_date.isoformat() for item in ordered]
    indicator_ids = [item.daily_indicator_id for item in ordered]
    batches = [{
        "batch_id": f"{patient_id}:created:{current_page}",
        "prompt_ids": [item.id for item in ordered],
        "indicator_ids": indicator_ids,
        "indicator_id": indicator_ids[0] if indicator_ids else None,
        "dates": dates,
        "date": dates[0] if dates else None,
        "status": "created",
    }] if ordered else []
    return {"prompts": batches, "pagination": {
        "page": current_page, "page_size": page_size, "total": total, "pages": pages,
    }}


@router.get("/api/patients/{patient_id}/atypical-days")
def api_atypical_days(
    patient_id: str,
    start_date: date | None = Query(default=None), end_date: date | None = Query(default=None),
    dates: str | None = Query(default=None, max_length=4000),
    page: int = Query(default=1, ge=1),
    page_size: PageSize = Query(default=PageSize.TEN),
    principal: SessionPrincipal = Depends(require_session), db: Session = Depends(get_db),
) -> dict[str, object]:
    if dates is None and start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must be before or equal to end_date.")
    exact_dates: list[date] | None = None
    if dates is not None:
        tokens = dates.split(",")
        if not tokens or any(not token for token in tokens) or len(tokens) > 366:
            raise HTTPException(status_code=400, detail="Invalid exact date filter.")
        try:
            parsed_dates = [date.fromisoformat(token) for token in tokens]
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid exact date filter.") from exc
        if any(day.isoformat() != token for day, token in zip(parsed_dates, tokens)):
            raise HTTPException(status_code=400, detail="Invalid exact date filter.")
        exact_dates = list(dict.fromkeys(parsed_dates))
    _require_patient_access(db, patient_id, principal)
    actor_role = "PATIENT" if principal.patient is not None else "DOCTOR"
    if start_date is not None or end_date is not None or exact_dates is not None:
        db.add(ProvenanceEvent(
            activity_type="PatientDetailFilterApplied", entity_type="patient", entity_id=patient_id,
            actor_user_id=principal.account.id, source_type="user", source_id=principal.account.id,
            metadata_json={
                "actor_role": actor_role,
                "start_date": start_date.isoformat() if start_date else None,
                "end_date": end_date.isoformat() if end_date else None,
                "dates": [item.isoformat() for item in exact_dates] if exact_dates is not None else None,
            },
        ))
    patient = db.get(Patient, patient_id)
    local_today = patient_local_datetime(datetime.utcnow(), patient.timezone if patient else None).date()
    view_start, view_end = local_date_utc_bounds(local_today, patient.timezone if patient else None)
    already_viewed = db.scalar(select(ProvenanceEvent.id).where(
        ProvenanceEvent.activity_type == "AtypicalDayDetailViewed",
        ProvenanceEvent.entity_type == "patient", ProvenanceEvent.entity_id == patient_id,
        ProvenanceEvent.actor_user_id == principal.account.id,
        ProvenanceEvent.occurred_at >= view_start, ProvenanceEvent.occurred_at < view_end,
    ).limit(1))
    if already_viewed is None:
        db.add(ProvenanceEvent(
            activity_type="AtypicalDayDetailViewed", entity_type="patient", entity_id=patient_id,
            actor_user_id=principal.account.id, source_type="user", source_id=principal.account.id,
            metadata_json={"actor_role": actor_role},
        ))
    latest_run = db.scalar(select(AnalysisRun).join(
        DailyIndicator, DailyIndicator.analysis_run_id == AnalysisRun.id,
    ).where(
        DailyIndicator.patient_id == patient_id,
        AnalysisRun.status == "completed",
    ).order_by(AnalysisRun.finished_at.desc(), AnalysisRun.created_at.desc()).limit(1))
    if latest_run is None:
        db.commit()
        return {"days": [], "pagination": {"page": 1, "page_size": page_size, "total": 0, "pages": 1}}
    query = select(DailyIndicator).where(
        DailyIndicator.analysis_run_id == latest_run.id,
        DailyIndicator.patient_id == patient_id,
        DailyIndicator.anomaly_flag.is_(True),
    )
    if exact_dates is not None:
        query = query.where(DailyIndicator.indicator_date.in_(exact_dates))
    elif start_date:
        query = query.where(DailyIndicator.indicator_date >= start_date)
    if exact_dates is None and end_date:
        query = query.where(DailyIndicator.indicator_date <= end_date)
    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
    pages = max(1, (total + page_size - 1) // page_size)
    current_page = min(page, pages)
    indicators = db.scalars(
        query.order_by(DailyIndicator.indicator_date.desc(), DailyIndicator.id)
        .offset((current_page - 1) * page_size).limit(page_size)
    ).all()
    active_link_id = None
    if principal.doctor is not None and (principal.patient is None or principal.patient.id != patient_id):
        active_link_id = db.scalar(select(PatientDoctorLink.id).where(
            PatientDoctorLink.patient_id == patient_id,
            PatientDoctorLink.doctor_id == principal.doctor.id,
            PatientDoctorLink.status == "ACTIVE",
        ))
    results = []
    for indicator in indicators:
        investigation_query = select(Investigation.id).where(
            Investigation.patient_id == patient_id,
            Investigation.atypical_day_event_id == indicator.id,
        )
        if principal.doctor is not None and (principal.patient is None or principal.patient.id != patient_id):
            investigation_query = investigation_query.where(
                Investigation.doctor_id == principal.doctor.id,
                Investigation.association_id == active_link_id,
            )
        results.append({
            "indicator_id": indicator.id,
            "date": indicator.indicator_date.isoformat(),
            "reason_summary": None,
            "has_investigation": db.scalar(investigation_query.limit(1)) is not None,
        })
    db.commit()
    return {"days": results, "pagination": {
        "page": current_page, "page_size": page_size, "total": total, "pages": pages,
    }}


@router.get("/api/patients/{patient_id}/provenance")
def api_patient_provenance(
    patient_id: str, limit: int = Query(default=50, ge=1, le=200),
    principal: SessionPrincipal = Depends(require_session), db: Session = Depends(get_db),
) -> dict[str, object]:
    _require_patient_access(db, patient_id, principal)
    from app.models.entities import AtypicalDayPrompt
    link_query = select(PatientDoctorLink.id).where(PatientDoctorLink.patient_id == patient_id)
    investigation_query = select(Investigation.id).where(Investigation.patient_id == patient_id)
    if principal.patient is None or principal.patient.id != patient_id:
        # Doctor context: only the currently authorized cycle. Earlier cycles'
        # links/investigations stay out, as re-association never restores them.
        active_link_id = db.scalar(select(PatientDoctorLink.id).where(
            PatientDoctorLink.patient_id == patient_id,
            PatientDoctorLink.doctor_id == principal.doctor.id,
            PatientDoctorLink.status == "ACTIVE",
        ))
        link_query = link_query.where(PatientDoctorLink.id == active_link_id)
        investigation_query = investigation_query.where(Investigation.association_id == active_link_id)
    link_ids = link_query
    investigation_ids = investigation_query
    prompt_ids = select(AtypicalDayPrompt.id).where(AtypicalDayPrompt.patient_id == patient_id)
    event_scope = or_(
        (ProvenanceEvent.entity_type == "patient") & (ProvenanceEvent.entity_id == patient_id)
        & ProvenanceEvent.activity_type.in_(("AtypicalDayDetailViewed", "PatientDetailFilterApplied")),
        (ProvenanceEvent.entity_type == "patient_doctor_link") & ProvenanceEvent.entity_id.in_(link_ids),
        (ProvenanceEvent.entity_type == "investigation") & ProvenanceEvent.entity_id.in_(investigation_ids),
        (ProvenanceEvent.entity_type == "atypical_day_prompt") & ProvenanceEvent.entity_id.in_(prompt_ids),
    )
    events = db.scalars(select(ProvenanceEvent).where(event_scope)
                        .order_by(ProvenanceEvent.occurred_at.desc()).limit(limit)).all()
    return {"events": [{
        "activity_type": event.activity_type,
        "occurred_at": event.occurred_at.isoformat(),
        "metadata": event.metadata_json or {},
    } for event in events]}


@router.post("/api/atypical-day-prompts/defer")
def api_atypical_day_prompt_batch_defer(
    payload: AtypicalPromptDeferBatchPayload,
    principal: SessionPrincipal = Depends(require_session), db: Session = Depends(get_db),
) -> dict[str, object]:
    if principal.patient is None:
        raise HTTPException(status_code=403, detail="Patient access required.")
    try:
        prompts = defer_prompt_batch(db, principal.patient.id, payload.indicator_ids, principal)
    except InvestigationNotFound as exc:
        raise HTTPException(status_code=404, detail="Prompt not found.") from exc
    except InvestigationConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"prompts": [{"indicator_id": item.daily_indicator_id, "status": item.status.lower()}
                        for item in prompts]}


@router.post("/api/atypical-day-prompts/{indicator_id}/defer")
def api_atypical_day_prompt_defer(
    indicator_id: str, principal: SessionPrincipal = Depends(require_session), db: Session = Depends(get_db),
) -> dict[str, object]:
    if principal.patient is None:
        raise HTTPException(status_code=403, detail="Patient access required.")
    try:
        prompt = defer_prompt(db, principal.patient.id, indicator_id, principal)
    except InvestigationNotFound as exc:
        raise HTTPException(status_code=404, detail="Prompt not found.") from exc
    except InvestigationConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"prompt": {"indicator_id": prompt.daily_indicator_id, "status": prompt.status.lower()}}


@router.get("/api/dashboard")
def api_dashboard(
    principal: SessionPrincipal = Depends(require_session),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    patient_ids = _scoped_patient_ids(db, principal)
    return {
        "metrics": {
            "patient_count": len(patient_ids),
            "normalized_count": db.scalar(
                select(func.count(GlucoseRecord.id)).where(GlucoseRecord.patient_id.in_(patient_ids))
            ) or 0,
            "indicator_count": db.scalar(
                select(func.count(DailyIndicator.id)).where(DailyIndicator.patient_id.in_(patient_ids))
            ) or 0,
            "issue_count": db.scalar(
                select(func.count(DataQualityIssue.id)).where(DataQualityIssue.patient_id.in_(patient_ids))
            ) or 0,
        },
        "links": {"latest_batch": [], "latest_run": []},
    }


def _scoped_patient_ids(db: Session, principal: SessionPrincipal) -> list[str]:
    """Patients the principal may list: itself, or a doctor's ACTIVE links only."""
    if principal.patient is not None:
        return [principal.patient.id]
    if principal.doctor is not None:
        return list(db.scalars(select(PatientDoctorLink.patient_id).where(
            PatientDoctorLink.doctor_id == principal.doctor.id,
            PatientDoctorLink.status == "ACTIVE",
        )))
    raise HTTPException(status_code=403, detail="Patient or doctor access required.")


def _require_patient_access(db: Session, patient_id: str, principal: SessionPrincipal) -> Patient:
    patient = db.get(Patient, patient_id)
    patient_access = principal.patient is not None and principal.patient.id == patient_id
    doctor_access = principal.doctor is not None and db.scalar(select(PatientDoctorLink.id).where(
        PatientDoctorLink.patient_id == patient_id,
        PatientDoctorLink.doctor_id == principal.doctor.id,
        PatientDoctorLink.status == "ACTIVE",
    )) is not None
    if patient is None or not (patient_access or doctor_access):
        # Do not reveal whether another patient's internal ID exists.
        raise HTTPException(status_code=404, detail="Patient not found.")
    return patient


@router.get("/api/patients")
def api_patients(
    page: int = Query(default=1, ge=1),
    page_size: PageSize = Query(default=PageSize.TEN),
    q: str | None = Query(default=None),
    signal: str | None = Query(default=None),
    principal: SessionPrincipal = Depends(require_session),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return get_paginated_patients(
        db,
        page=page,
        page_size=page_size,
        query=q,
        signal=signal,
        patient_ids=_scoped_patient_ids(db, principal),
    )


@router.post("/api/patients", status_code=201)
def api_create_patient(
    payload: PatientCreatePayload | None = None,
    principal: SessionPrincipal = Depends(require_session),
) -> dict[str, object]:
    # Account/profile creation must be atomic through /api/auth/register.
    raise HTTPException(status_code=403, detail="Use account registration to create a patient.")


@router.get("/api/patients/{patient_id}")
def api_patient_detail(
    patient_id: str,
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    dates: str | None = Query(default=None, max_length=4000),
    indicator_page: int = Query(default=1, ge=1),
    indicator_page_size: PageSize = Query(default=PageSize.TEN),
    event_page: int = Query(default=1, ge=1),
    event_page_size: PageSize = Query(default=PageSize.TEN),
    principal: SessionPrincipal = Depends(require_session),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    _require_patient_access(db, patient_id, principal)
    exact_dates: list[date] | None = None
    if dates is not None:
        tokens = dates.split(",")
        if not tokens or any(not token for token in tokens) or len(tokens) > 366:
            raise HTTPException(status_code=400, detail="Invalid exact date filter.")
        try:
            parsed_dates = [date.fromisoformat(token) for token in tokens]
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid exact date filter.") from exc
        if any(day.isoformat() != token for day, token in zip(parsed_dates, tokens)):
            raise HTTPException(status_code=400, detail="Invalid exact date filter.")
        exact_dates = list(dict.fromkeys(parsed_dates))
    context = get_patient_detail_context(
        db, patient_id, start_date=start_date, end_date=end_date, exact_dates=exact_dates,
        indicator_page=indicator_page, indicator_page_size=indicator_page_size,
        event_page=event_page, event_page_size=event_page_size,
    )
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
        "daily_indicators_page": context["daily_indicators_page_json"],
        "daily_indicators_pagination": context["daily_indicators_pagination"],
        "glucose_events": context["glucose_events_json"],
        "recent_events": context["recent_events_json"],
        "recent_events_pagination": context["recent_events_pagination"],
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
    principal: SessionPrincipal = Depends(require_session),
    db: Session = Depends(get_db),
) -> Response:
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must be before or equal to end_date.")

    if lang not in SUPPORTED_REPORT_LANGS:
        lang = "pt-BR"

    _require_patient_access(db, patient_id, principal)
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
    principal: SessionPrincipal = Depends(require_session),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    patient = _require_patient_access(db, patient_id, principal)
    if principal.patient is None or principal.patient.id != patient_id:
        raise HTTPException(status_code=403, detail="Patient access required.")
    record = create_manual_glucose_record(
        db,
        patient=patient,
        measured_at=payload.measured_at,
        glucose_mg_dl=payload.glucose_mg_dl,
        context_label=payload.context_label,
        notes=payload.notes,
        actor_user_id=principal.account.id,
    )
    return {
        "glucose_record": {
            "id": record.id,
            "patient_id": record.patient_id,
            "measured_at": patient_local_datetime(record.measured_at, patient.timezone).replace(tzinfo=None).isoformat(),
            "glucose_mg_dl": record.glucose_mg_dl,
            "context_label": record.context_label,
            "analytics_status": "stale",
        }
    }
