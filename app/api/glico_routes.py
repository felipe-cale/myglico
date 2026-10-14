from __future__ import annotations

from datetime import date, datetime, timedelta
import re
import math
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
import httpx
import hashlib
import hmac
import secrets
import time
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.security import SessionPrincipal, require_session
from app.core.config import get_settings
from app.db.session import get_db
from app.models.entities import (AnalysisRun, DailyIndicator, DailyMetricsCurrent, GlucoseRecord,
                                 Investigation, Patient, PatientDoctorLink)
from app.models.glico import GlicoConversation, GlicoExecution, GlicoProposal, GlicoProposalRevision, GlicoRequestReplay
from app.services.glico import (
    LOCALES, active_context, authorized_conversation, consume_quota, create_execution,
    cleanup_expired_glico_replays, create_proposal, invalidate_proposals, proposal_payload, require_csrf,
    release_media_job, reserve_media_job, serialize_proposal,
)
from app.services.manual_entry import create_manual_glucose_record
from app.core.patient_time import local_range_utc_bounds

router = APIRouter()

def _require_glico_enabled() -> None:
    if not get_settings().glico_enabled:
        raise HTTPException(status_code=503, detail="capability_unavailable")


class ConversationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    locale: str = "pt-BR"
    client_request_id: str = Field(min_length=36, max_length=36)

    @field_validator("locale")
    @classmethod
    def validate_locale(cls, value: str) -> str:
        if value not in LOCALES:
            raise ValueError("unsupported locale")
        return value


class ContextUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=1)
    patient_id: str | None = Field(default=None, min_length=36, max_length=36)
    doctor_id: str | None = Field(default=None, min_length=36, max_length=36)
    period_start: date | None = None
    period_end: date | None = None


class HistoryTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["user", "assistant"]
    text: str = Field(min_length=1, max_length=600)


class MessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=2000)
    history: list[HistoryTurn] = Field(default_factory=list, max_length=6)
    context_version: int = Field(ge=1)
    client_request_id: str = Field(min_length=36, max_length=36)


class ProposalEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=1)
    context_version: int = Field(ge=1)
    fields: dict = Field(max_length=16)


class ConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=1)
    context_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=36, max_length=36)


class CancelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=1)


class CollaborationProposalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str
    investigation_id: str | None = Field(default=None, min_length=36, max_length=36)
    title: str | None = Field(default=None, min_length=1, max_length=180)
    content: str = Field(min_length=1, max_length=10000)


def _uuid(value: str) -> bool:
    try:
        UUID(value)
        return True
    except (ValueError, TypeError):
        return False


def _trusted_worker_assessment(result: dict, media_kind: str) -> float | None:
    """Return the worker's candidate only when its explicit quality gate passes."""
    assessment = result.get("assessment")
    if not isinstance(assessment, dict):
        return None
    if (assessment.get("needs_clarification") is not False
            or assessment.get("status") != "review_required"
            or assessment.get("ambiguity") is True
            or assessment.get("ambiguous") is True):
        return None
    reasons = assessment.get("clarification_reasons", [])
    if not isinstance(reasons, list) or reasons:
        return None
    value = assessment.get("candidate_value_mg_dl")
    confidence = assessment.get("candidate_confidence")
    threshold = assessment.get("confidence_threshold")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        return None
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
        return None
    value = float(value)
    confidence = float(confidence)
    threshold = float(threshold)
    minimum_confidence = 0.75 if media_kind == "image" else 0.55
    if not (math.isfinite(value) and math.isfinite(confidence) and math.isfinite(threshold)
            and 20 <= value <= 600 and confidence >= max(threshold, minimum_confidence)):
        return None
    return value


def _require_csrf(request: Request, principal: SessionPrincipal) -> None:
    require_csrf(request, principal)


def _context_payload(db: Session, item: GlicoConversation) -> dict:
    link = db.get(PatientDoctorLink, item.association_id) if item.association_id else None
    return {"patient_id": item.patient_id, "association_id": item.association_id,
            "association_active": bool(link and link.status == "ACTIVE"),
            "period_start": item.period_start, "period_end": item.period_end,
            "version": item.context_version}


def _conversation(db: Session, item: GlicoConversation, principal: SessionPrincipal) -> dict:
    proposals = db.scalars(select(GlicoProposal).where(
        GlicoProposal.conversation_id == item.id,
        GlicoProposal.owner_account_id == principal.account.id,
        GlicoProposal.expires_at > datetime.utcnow(),
    ).order_by(GlicoProposal.created_at.desc()).limit(10)).all()
    cards = []
    for proposal in proposals:
        if proposal.state in {"DRAFT", "READY"}:
            cards.append({"type": "proposal", "proposal": serialize_proposal(proposal)})
        elif proposal.state == "EXECUTED":
            receipt = db.scalar(select(GlicoExecution).where(
                GlicoExecution.proposal_id == proposal.id,
                GlicoExecution.proposal_version == proposal.version,
            ))
            if receipt:
                cards.append({"type": "receipt", "receipt": _receipt(receipt)})
    return {"id": item.id, "role": item.role, "context": _context_payload(db, item),
            "context_version": item.context_version, "locale": item.locale, "cards": cards,
            "capabilities": _capabilities(principal)}


def _capabilities(principal: SessionPrincipal) -> dict:
    settings = get_settings()
    worker = bool(settings.glico_media_worker_url and settings.glico_media_worker_secret
                  and len(settings.glico_media_worker_secret.encode()) >= 32
                  and settings.glico_media_global_jobs > 0)
    return {"text": settings.glico_enabled, "faq": settings.glico_enabled,
            "language_model": bool(settings.glico_enabled and settings.gemini_api_key),
            "photo": bool(settings.glico_enabled and settings.glico_photo_enabled and worker
                          and principal.doctor is None),
            "audio": bool(settings.glico_enabled and settings.glico_audio_enabled and worker)}


def _replay_response(db: Session, principal: SessionPrincipal, operation: str, request_id: str,
                    conversation_id: str, digest: str) -> dict | None:
    row = db.scalar(select(GlicoRequestReplay).where(
        GlicoRequestReplay.owner_account_id == principal.account.id,
        GlicoRequestReplay.operation == operation,
        GlicoRequestReplay.client_request_id == request_id))
    if row is None:
        return None
    if row.expires_at <= datetime.utcnow():
        db.delete(row)
        db.flush()
        return None
    if row.conversation_id != conversation_id or row.request_digest != digest:
        raise HTTPException(status_code=409, detail="idempotency_conflict")
    from app.core.crypto import decrypt_field
    import json
    try:
        return json.loads(decrypt_field(row.response_encrypted, table="glico_request_replays",
                                        column="response", record_id=row.id))
    except Exception:
        raise HTTPException(status_code=503, detail="capability_unavailable") from None


def _save_replay(db: Session, principal: SessionPrincipal, conversation: GlicoConversation,
                 operation: str, request_id: str, digest: str, response: dict) -> None:
    from app.core.crypto import encrypt_field
    import json
    row = GlicoRequestReplay(conversation_id=conversation.id, owner_account_id=principal.account.id,
        operation=operation, client_request_id=request_id, request_digest=digest,
        response_encrypted=b"", expires_at=datetime.utcnow() + timedelta(hours=24))
    db.add(row)
    db.flush()
    row.response_encrypted = encrypt_field(json.dumps(response, sort_keys=True, separators=(",", ":")),
        table="glico_request_replays", column="response", record_id=row.id)


def _receipt(item: GlicoExecution) -> dict:
    return {"execution_id": item.id, "proposal_id": item.proposal_id,
            "version": item.proposal_version, "operation": item.operation,
            "result_type": item.result_type, "result_id": item.result_id,
            "committed_at": item.committed_at.isoformat() + "Z",
            "analytics_status": item.analytics_status}


def _make_proposal(db: Session, conversation: GlicoConversation, text: str):
    # Deliberately deterministic. No external model receives clinical context or text.
    if re.search(r"\b(hi|lo)\b", text, re.I):
        return {"type": "clarification", "answer_key": "glico.reading.unsupported_signal"}
    unit_match = re.search(r"\b(mg\s*/?\s*dl|mmol\s*/?\s*l)\b", text, re.I)
    iso_date = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", text)
    clock = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", text)
    numeric_text = text
    for matched in (unit_match, iso_date, clock):
        if matched:
            numeric_text = numeric_text.replace(matched.group(0), " ", 1)
    number_matches = re.findall(r"(?<!\d)(\d{1,4}(?:[.,]\d{1,2})?)(?!\d)", numeric_text)
    if len(number_matches) > 1:
        return {"type": "clarification", "answer_key": "glico.reading.multiple_values"}
    number = re.search(r"(?<!\d)(\d{1,4}(?:[.,]\d{1,2})?)(?!\d)", numeric_text)
    if number and unit_match:
        value = float(number.group(1).replace(",", "."))
        source_unit = re.sub(r"\s+", "", unit_match.group(1).lower())
        unit = source_unit.replace("/", "")
        if unit in {"mmoll", "mmol/l"}:
            mg_dl = round(value * 18.0182, 1)
            normalized_unit = "mmol/L"
        else:
            mg_dl = value
            normalized_unit = "mg/dL"
        measured_at = None
        patient = db.get(Patient, conversation.patient_id) if conversation.patient_id else None
        if iso_date and clock:
            try:
                from zoneinfo import ZoneInfo
                local = datetime.fromisoformat(f"{iso_date.group(1)}T{clock.group(0)}:00").replace(
                    tzinfo=ZoneInfo(patient.timezone if patient else "UTC"))
                measured_at = local.isoformat()
            except (ValueError, KeyError):
                measured_at = None
        missing = [] if measured_at else ["measured_at"]
        fields = {"glucose_mg_dl": mg_dl, "original_value": value,
                  "original_unit": normalized_unit if source_unit.startswith("mg") else "mmol/L",
                  "measured_at": measured_at, "timezone": patient.timezone if patient else "UTC",
                  "context_label": None, "notes": None}
        valid = 20 <= mg_dl <= 600
        if not valid:
            return {"type": "clarification", "answer_key": "glico.reading.out_of_range"}
        proposal = create_proposal(db, conversation, kind="glucose_single", fields=fields,
                                   origin="glico_text", ready=valid and not missing)
        payload = proposal_payload(proposal)
        payload["missing_fields"] = missing
        from app.core.crypto import encrypt_field
        import json
        proposal.payload_encrypted = encrypt_field(
            json.dumps(payload, sort_keys=True, separators=(",", ":")),
            table="glico_proposals", column="payload", record_id=proposal.id,
        )
        revision = db.scalar(select(GlicoProposalRevision).where(
            GlicoProposalRevision.proposal_id == proposal.id, GlicoProposalRevision.version == proposal.version))
        if revision:
            revision.payload_encrypted = proposal.payload_encrypted
        return {"type": "proposal", "proposal": serialize_proposal(proposal)}
    return None


_LLM_QUERY_KEYWORD = {
    "query_readings": "leituras", "query_metrics": "resumo", "query_atypical_days": "atípicos",
    "query_investigations": "questionamentos", "query_linked_patients": "meus pacientes",
}


def _language_model_result(db: Session, conversation: GlicoConversation, principal: SessionPrincipal,
                           text: str, history: list, spoken: bool = False) -> dict | None:
    """Let the optional model pick an intent; execution stays on the deterministic handlers.

    Returns None whenever the model is off, unavailable, or its output cannot be trusted, so the
    caller falls back to the keyword assistant. Nothing here is written without a proposal review.
    """
    settings = get_settings()
    if not getattr(settings, "gemini_api_key", None) or conversation.patient_id is None:
        return None
    from zoneinfo import ZoneInfo
    from app.services.glico_llm import DOSE_REFUSAL, OFF_TOPIC_REPLY, interpret, is_dose_question
    if is_dose_question(text):
        return {"type": "message", "text": DOSE_REFUSAL.get(conversation.locale, DOSE_REFUSAL["pt-BR"])}
    patient = db.get(Patient, conversation.patient_id)
    zone = patient.timezone if patient and patient.timezone else "UTC"
    try:
        now = datetime.now(ZoneInfo(zone))
    except (KeyError, ValueError):
        zone, now = "UTC", datetime.utcnow()
    intent = interpret(
        api_key=settings.gemini_api_key, model=settings.gemini_model,
        timeout=settings.gemini_timeout_seconds, text=text,
        history=[{"role": turn.role, "text": turn.text} for turn in history],
        locale=conversation.locale, role=conversation.role,
        now_iso=now.strftime("%Y-%m-%d %H:%M"), timezone=zone)
    if intent is None:
        return None
    kind = intent["intent"]
    if kind == "record_reading":
        if principal.doctor is not None:
            raise HTTPException(status_code=403, detail="operation_not_allowed")
        value = intent["glucose_value"]
        # The model must not invent numbers: the value has to be present in what the user typed.
        # Spoken numbers ("cento e vinte") are transcribed as words, so audio is exempt; the
        # proposal still goes through range validation and the user's review.
        typed = text.replace(",", ".")
        if not spoken and not re.search(rf"(?<!\d){re.escape(format(value, 'g'))}(?!\d)", typed):
            return None
        parts = [f"{format(value, 'g')} {intent['unit']}"]
        if intent.get("measured_date"):
            parts.append(f"{intent['measured_date']} {intent['measured_time']}")
        return _make_proposal(db, conversation, " ".join(parts))
    if kind in _LLM_QUERY_KEYWORD:
        return _query_answer(db, conversation, _LLM_QUERY_KEYWORD[kind])
    if kind == "pdf_report":
        return {"type": "answer", "answer_key": "glico.query.pdf"}
    if kind == "off_topic":
        # Fixed text on purpose: the model never writes the reply to out-of-scope requests.
        return {"type": "message", "text": OFF_TOPIC_REPLY.get(conversation.locale, OFF_TOPIC_REPLY["pt-BR"])}
    if kind == "answer" and intent["reply"]:
        return {"type": "message", "text": intent["reply"]}
    return None


_FAQ = {
    "registro": {
        "pt-BR": "Para registrar, informe valor, unidade, data e hora; revise a proposta e confirme no cartão.",
        "en-US": "To add a reading, provide value, unit, date and time; review the proposal and confirm its card.",
        "es": "Para registrar, indique valor, unidad, fecha y hora; revise la propuesta y confírmela en la tarjeta.",
    },
    "pdf": {
        "pt-BR": "Abra o relatório do paciente e escolha um intervalo de datas e o idioma do PDF.",
        "en-US": "Open the patient report and choose a date range and PDF language.",
        "es": "Abra el informe del paciente y elija un intervalo de fechas y el idioma del PDF.",
    },
    "pending": {
        "pt-BR": "Pending indica que métricas básicas foram atualizadas e a classificação analítica aguarda processamento.",
        "en-US": "Pending means basic metrics were updated and analytical classification is awaiting processing.",
        "es": "Pending indica que las métricas básicas se actualizaron y la clasificación analítica espera procesamiento.",
    },
}


def _query_answer(db: Session, conversation: GlicoConversation, text: str) -> dict | None:
    """Resolve only documented, bounded read intents against the selected context."""
    lower = text.casefold()
    locale = conversation.locale
    faq_key = "registro" if any(x in lower for x in ("como registrar", "how to add", "how do i add", "cómo registrar")) else (
        "pdf" if "pdf" in lower or "relatório" in lower or "report" in lower or "informe" in lower else (
        "pending" if "pending" in lower or "pendente" in lower or "stale" in lower else None))
    if faq_key:
        return {"type": "help", "answer": _FAQ[faq_key][locale], "links": ["/", "/patients"]}
    if conversation.patient_id is None:
        if conversation.role == "doctor" and any(x in lower for x in ("patients", "my patients", "meus pacientes", "pacientes", "mis pacientes")):
            from app.models.entities import Doctor, PatientDoctorLink
            doctor_id = conversation_owner_domain_id(db, conversation.owner_account_id)
            rows = db.execute(select(Patient.id, Patient.short_id, Patient.name).join(
                PatientDoctorLink, PatientDoctorLink.patient_id == Patient.id).where(
                PatientDoctorLink.doctor_id == doctor_id, PatientDoctorLink.status == "ACTIVE"
            ).order_by(Patient.short_id).limit(50)).all()
            return {"type": "answer", "answer_key": "glico.query.linked_patients",
                    "items": [{"patient_id": r.id, "short_id": r.short_id, "name": r.name} for r in rows]}
        return None
    if re.search(r"\d\s*(mg\s*/?\s*dl|mmol\s*/?\s*l)\b", lower):
        return None  # a value with its unit is a reading to record, never a query
    wants_readings = any(x in lower for x in ("leitura", "leituras", "reading", "readings", "glicemia", "glucose"))
    wants_summary = any(x in lower for x in ("resumo", "summary", "métrica", "metric", "media", "average"))
    wants_cases = any(x in lower for x in ("atíp", "atip", "anomal", "atypical"))
    wants_threads = any(x in lower for x in ("questionamento", "investiga", "mensagem", "conversation"))
    if wants_threads:
        query = select(Investigation.id, Investigation.status, Investigation.opened_at).where(
            Investigation.patient_id == conversation.patient_id)
        if conversation.role == "doctor":
            query = query.where(Investigation.doctor_id == conversation_owner_domain_id(db, conversation.owner_account_id),
                                Investigation.association_id == conversation.association_id)
        rows = db.execute(query.order_by(Investigation.opened_at.desc()).limit(20)).all()
        return {"type": "answer", "answer_key": "glico.query.investigations", "items": [
            {"id": r.id, "status": r.status.lower(), "opened_at": r.opened_at.isoformat()} for r in rows]}
    if wants_readings:
        query = select(GlucoseRecord).where(GlucoseRecord.patient_id == conversation.patient_id)
        patient = db.get(Patient, conversation.patient_id)
        if conversation.period_start and patient:
            start, _ = local_range_utc_bounds(date.fromisoformat(conversation.period_start), date.fromisoformat(conversation.period_start), patient.timezone)
            query = query.where(GlucoseRecord.measured_at >= start)
        if conversation.period_end and patient:
            _, end = local_range_utc_bounds(date.fromisoformat(conversation.period_end), date.fromisoformat(conversation.period_end), patient.timezone)
            query = query.where(GlucoseRecord.measured_at < end)
        rows = db.scalars(query.order_by(GlucoseRecord.measured_at.desc(), GlucoseRecord.id).limit(50)).all()
        return {"type": "answer", "answer_key": "glico.query.readings", "items": [
            {"measured_at": r.measured_at.isoformat() + "Z", "glucose_mg_dl": r.glucose_mg_dl,
             "context_label": r.context_label} for r in rows], "truncated": len(rows) == 50}
    if wants_summary:
        query = select(DailyMetricsCurrent).where(DailyMetricsCurrent.patient_id == conversation.patient_id)
        if conversation.period_start:
            query = query.where(DailyMetricsCurrent.metric_date >= date.fromisoformat(conversation.period_start))
        if conversation.period_end:
            query = query.where(DailyMetricsCurrent.metric_date <= date.fromisoformat(conversation.period_end))
        rows = db.scalars(query.order_by(DailyMetricsCurrent.metric_date.desc()).limit(366)).all()
        return {"type": "answer", "answer_key": "glico.query.metrics", "items": [
            {"date": r.metric_date.isoformat(), "count": r.glucose_event_count, "avg_glucose": r.avg_glucose,
             "min_glucose": r.min_glucose, "max_glucose": r.max_glucose,
             "freshness": r.freshness_status} for r in rows]}
    if wants_cases:
        run = db.scalar(select(AnalysisRun).where(AnalysisRun.patient_id == conversation.patient_id,
            AnalysisRun.status == "completed").order_by(AnalysisRun.finished_at.desc(), AnalysisRun.created_at.desc()).limit(1))
        if run is None:
            return {"type": "answer", "answer_key": "glico.query.no_current_classification", "items": []}
        fresh_days = select(DailyMetricsCurrent.metric_date).where(
            DailyMetricsCurrent.patient_id == conversation.patient_id,
            DailyMetricsCurrent.freshness_status != "fresh")
        rows = db.scalars(select(DailyIndicator).where(DailyIndicator.patient_id == conversation.patient_id,
            DailyIndicator.analysis_run_id == run.id, DailyIndicator.anomaly_flag.is_(True),
            DailyIndicator.indicator_date.not_in(fresh_days)).order_by(DailyIndicator.indicator_date.desc()).limit(50)).all()
        return {"type": "answer", "answer_key": "glico.query.atypical_days", "items": [
            {"date": r.indicator_date.isoformat(), "indicator_id": r.id, "score": r.anomaly_score} for r in rows]}
    return None


def conversation_owner_domain_id(db: Session, account_id: str) -> str | None:
    from app.models.entities import Doctor
    return db.scalar(select(Doctor.id).where(Doctor.user_account_id == account_id))


@router.get("/api/glico/csrf")
def glico_csrf(principal: SessionPrincipal = Depends(require_session)) -> dict[str, str]:
    from app.services.glico import csrf_token
    return {"token": csrf_token(principal.session.id)}


@router.get("/api/glico/capabilities")
def glico_capabilities(locale: str = "pt-BR", principal: SessionPrincipal = Depends(require_session)) -> dict:
    if locale not in LOCALES:
        raise HTTPException(status_code=422, detail="invalid_fields")
    flags = _capabilities(principal)
    return {"locale": locale, "phase": "F1", **flags, "external_language_provider": bool(get_settings().gemini_api_key),
            "limits": {"text_chars": 2000, "photo_bytes": 3145728, "audio_bytes": 3145728,
                       "audio_seconds": 60, "proposal_ttl_seconds": 900}}


@router.post("/api/glico/conversations", status_code=201)
def create_conversation(payload: ConversationCreate, request: Request, db: Session = Depends(get_db),
                        principal: SessionPrincipal = Depends(require_session)) -> dict:
    _require_glico_enabled()
    _require_csrf(request, principal)
    if not _uuid(payload.client_request_id) or payload.locale not in LOCALES:
        raise HTTPException(status_code=422, detail="invalid_fields")
    existing = db.scalar(select(GlicoConversation).where(
        GlicoConversation.owner_account_id == principal.account.id,
        GlicoConversation.client_request_id == payload.client_request_id,
    ))
    if existing is not None:
        return _conversation(db, authorized_conversation(db, existing.id, principal), principal)
    patient_id = principal.patient.id if principal.patient else None
    item = GlicoConversation(owner_account_id=principal.account.id,
        role="patient" if principal.patient else "doctor", client_request_id=payload.client_request_id, patient_id=patient_id,
        context_version=1, locale=payload.locale, expires_at=datetime.utcnow() + timedelta(hours=12))
    db.add(item)
    db.commit()
    db.refresh(item)
    return _conversation(db, item, principal)


@router.patch("/api/glico/conversations/{conversation_id}/context")
def update_context(conversation_id: str, payload: ContextUpdate, request: Request,
                   db: Session = Depends(get_db), principal: SessionPrincipal = Depends(require_session)) -> dict:
    _require_glico_enabled()
    _require_csrf(request, principal)
    item = authorized_conversation(db, conversation_id, principal, lock=True)
    if item.context_version != payload.version:
        raise HTTPException(status_code=409, detail="context_changed")
    if payload.period_start and payload.period_end and payload.period_start > payload.period_end:
        raise HTTPException(status_code=422, detail="invalid_fields")
    if payload.period_start and payload.period_end and (payload.period_end - payload.period_start).days > 365:
        raise HTTPException(status_code=422, detail="invalid_fields")
    patient_id = item.patient_id
    association_id = item.association_id
    if principal.doctor:
        if payload.doctor_id is not None:
            raise HTTPException(status_code=422, detail="invalid_fields")
        patient_id, association_id = active_context(db, principal, payload.patient_id)
    elif principal.patient:
        if payload.patient_id is not None:
            raise HTTPException(status_code=404, detail="resource_not_found")
        association_id = None
        if payload.doctor_id:
            link = db.scalar(select(PatientDoctorLink).where(
                PatientDoctorLink.patient_id == principal.patient.id,
                PatientDoctorLink.doctor_id == payload.doctor_id,
                PatientDoctorLink.status == "ACTIVE").with_for_update())
            if link is None:
                raise HTTPException(status_code=404, detail="resource_not_found")
            association_id = link.id
    item.patient_id = patient_id
    item.association_id = association_id
    item.context_version += 1
    item.period_start = payload.period_start.isoformat() if payload.period_start else None
    item.period_end = payload.period_end.isoformat() if payload.period_end else None
    item.updated_at = datetime.utcnow()
    invalidate_proposals(db, item.id)
    db.commit()
    return _conversation(db, item, principal)


@router.get("/api/glico/conversations/{conversation_id}")
def get_conversation(conversation_id: str, db: Session = Depends(get_db),
                     principal: SessionPrincipal = Depends(require_session)) -> dict:
    _require_glico_enabled()
    item = authorized_conversation(db, conversation_id, principal)
    return _conversation(db, item, principal)


@router.post("/api/glico/conversations/{conversation_id}/messages")
def send_message(conversation_id: str, payload: MessageRequest, request: Request,
                 db: Session = Depends(get_db), principal: SessionPrincipal = Depends(require_session)) -> dict:
    _require_glico_enabled()
    _require_csrf(request, principal)
    item = authorized_conversation(db, conversation_id, principal, lock=True)
    if payload.context_version != item.context_version:
        raise HTTPException(status_code=409, detail="context_changed")
    if not _uuid(payload.client_request_id):
        raise HTTPException(status_code=422, detail="invalid_fields")
    text = payload.text.strip()
    cleanup_expired_glico_replays(db)
    digest = hashlib.sha256(f"{conversation_id}\n{payload.context_version}\n{item.locale}\n{text}".encode()).hexdigest()
    replay = _replay_response(db, principal, "message", payload.client_request_id, conversation_id, digest)
    if replay is not None:
        return replay
    result = _language_model_result(db, item, principal, text, payload.history)
    if result is None:
        result = _query_answer(db, item, text)
    if result is None:
        if item.patient_id is None:
            raise HTTPException(status_code=409, detail="context_changed")
        if principal.doctor is not None and re.search(r"\b(mg\s*/?\s*dl|mmol\s*/?\s*l)\b", text, re.I):
            raise HTTPException(status_code=403, detail="operation_not_allowed")
        result = _make_proposal(db, item, text)
    if result is None:
        result = {"type": "help", "answer_key": "glico.help.try_manual",
                  "links": ["/", "/patients"]}
    consume_quota(db, principal.account.id, "messages_minute", 10)
    _save_replay(db, principal, item, "message", payload.client_request_id, digest, result)
    db.commit()
    return result


@router.patch("/api/glico/proposals/{proposal_id}")
def edit_proposal(proposal_id: str, payload: ProposalEdit, request: Request,
                  db: Session = Depends(get_db), principal: SessionPrincipal = Depends(require_session)) -> dict:
    _require_glico_enabled()
    _require_csrf(request, principal)
    candidate = db.scalar(select(GlicoProposal).where(
        GlicoProposal.id == proposal_id, GlicoProposal.owner_account_id == principal.account.id))
    if candidate is None:
        raise HTTPException(status_code=404, detail="resource_not_found")
    conversation = authorized_conversation(db, candidate.conversation_id, principal, lock=True)
    # UPDATE is also an effective serialization point on SQLite, where
    # SELECT FOR UPDATE is ignored; MySQL takes the same row lock here.
    db.execute(update(GlicoProposal).where(GlicoProposal.id == proposal_id,
        GlicoProposal.owner_account_id == principal.account.id).values(version=GlicoProposal.version))
    item = db.scalar(select(GlicoProposal).where(
        GlicoProposal.id == proposal_id, GlicoProposal.owner_account_id == principal.account.id)
        .with_for_update().execution_options(populate_existing=True))
    if item is None:
        raise HTTPException(status_code=404, detail="resource_not_found")
    if item.state not in {"DRAFT", "READY"} or item.expires_at <= datetime.utcnow():
        raise HTTPException(status_code=410, detail="proposal_expired")
    if payload.version != item.version or payload.context_version != conversation.context_version or item.context_version != conversation.context_version:
        raise HTTPException(status_code=409, detail="proposal_version_conflict")
    allowed = ({"glucose_mg_dl", "original_value", "original_unit", "measured_at", "timezone", "context_label", "notes"}
               if item.kind == "glucose_single" else {"title", "content"} if item.kind == "investigation_open"
               else {"content"} if item.kind == "investigation_message" else set())
    if not allowed or set(payload.fields) - allowed:
        raise HTTPException(status_code=422, detail="invalid_fields")
    fields = proposal_payload(item).get("fields", {})
    fields.update(payload.fields)
    if item.kind == "glucose_single":
        try:
            value = float(fields.get("glucose_mg_dl"))
        except (TypeError, ValueError, OverflowError):
            raise HTTPException(status_code=422, detail="invalid_fields") from None
        if not (20 <= value <= 600):
            raise HTTPException(status_code=422, detail="invalid_fields")
        try:
            measured_at = datetime.fromisoformat(fields.get("measured_at", ""))
            if measured_at.tzinfo is None:
                raise ValueError
        except (TypeError, ValueError, OverflowError):
            item.state = "DRAFT"
        else:
            item.state = "READY"
    else:
        valid = (isinstance(fields.get("content"), str) and bool(fields["content"].strip())
                 and len(fields["content"]) <= 10000)
        if item.kind == "investigation_open":
            valid = valid and isinstance(fields.get("title"), str) and bool(fields["title"].strip()) and len(fields["title"]) <= 180
        if not valid:
            raise HTTPException(status_code=422, detail="invalid_fields")
        item.state = "READY"
    item.version += 1
    item.context_version = conversation.context_version
    from app.core.crypto import encrypt_field
    import json
    from app.services.glico import _digest
    encrypted = encrypt_field(json.dumps({"fields": fields, "missing_fields": [], "warnings": []}, sort_keys=True, separators=(",", ":"), allow_nan=False), table="glico_proposals", column="payload", record_id=item.id)
    item.payload_encrypted = encrypted
    item.digest = _digest({"kind": item.kind, "fields": fields, "patient": item.patient_id,
                           "association": item.association_id, "owner": item.owner_account_id,
                           "version": item.version, "context_version": item.context_version, "normalizer": 1})
    item.updated_at = datetime.utcnow()
    db.add(GlicoProposalRevision(proposal_id=item.id, version=item.version,
        context_version=item.context_version, payload_encrypted=encrypted, digest=item.digest))
    db.commit()
    return {"proposal": serialize_proposal(item)}


@router.post("/api/glico/conversations/{conversation_id}/collaboration-proposals", status_code=201)
def prepare_collaboration(conversation_id: str, payload: CollaborationProposalRequest, request: Request,
                          db: Session = Depends(get_db), principal: SessionPrincipal = Depends(require_session)) -> dict:
    _require_glico_enabled()
    _require_csrf(request, principal)
    conversation = authorized_conversation(db, conversation_id, principal, lock=True)
    if conversation.patient_id is None or conversation.association_id is None:
        raise HTTPException(status_code=409, detail="context_changed")
    if payload.kind not in {"investigation_open", "investigation_message"}:
        raise HTTPException(status_code=422, detail="invalid_fields")
    active_patient, active_link_id = active_context(db, principal, conversation.patient_id)
    if active_patient != conversation.patient_id or active_link_id != conversation.association_id:
        # Patient conversations resolve their selected link independently from active_context.
        link = db.scalar(select(PatientDoctorLink).where(PatientDoctorLink.id == conversation.association_id,
            PatientDoctorLink.patient_id == conversation.patient_id, PatientDoctorLink.status == "ACTIVE"))
        if principal.patient is None or link is None:
            raise HTTPException(status_code=404, detail="resource_not_found")
    fields = {"content": payload.content.strip()}
    if not fields["content"]:
        raise HTTPException(status_code=422, detail="invalid_fields")
    if payload.kind == "investigation_open":
        if payload.investigation_id is not None or not payload.title or not payload.title.strip():
            raise HTTPException(status_code=422, detail="invalid_fields")
        fields["title"] = payload.title.strip()
    else:
        if not payload.investigation_id or payload.title is not None:
            raise HTTPException(status_code=422, detail="invalid_fields")
        from app.services.investigations import InvestigationNotFound, authorized_investigation
        try:
            investigation, _, _ = authorized_investigation(db, payload.investigation_id, principal)
        except InvestigationNotFound:
            raise HTTPException(status_code=404, detail="resource_not_found") from None
        if (investigation.patient_id != conversation.patient_id
                or investigation.association_id != conversation.association_id):
            raise HTTPException(status_code=404, detail="resource_not_found")
        fields["investigation_id"] = investigation.id
    proposal = create_proposal(db, conversation, kind=payload.kind, fields=fields,
                               origin="glico_collaboration", ready=True)
    db.commit()
    return {"proposal": serialize_proposal(proposal)}


@router.post("/api/glico/proposals/{proposal_id}/confirm")
def confirm_proposal(proposal_id: str, payload: ConfirmRequest, request: Request,
                     db: Session = Depends(get_db), principal: SessionPrincipal = Depends(require_session)) -> dict:
    _require_glico_enabled()
    _require_csrf(request, principal)
    candidate = db.scalar(select(GlicoProposal).where(
        GlicoProposal.id == proposal_id, GlicoProposal.owner_account_id == principal.account.id))
    if candidate is None:
        raise HTTPException(status_code=404, detail="resource_not_found")
    conversation = authorized_conversation(db, candidate.conversation_id, principal, lock=True)
    db.execute(update(GlicoProposal).where(GlicoProposal.id == proposal_id,
        GlicoProposal.owner_account_id == principal.account.id).values(version=GlicoProposal.version))
    item = db.scalar(select(GlicoProposal).where(
        GlicoProposal.id == proposal_id, GlicoProposal.owner_account_id == principal.account.id)
        .with_for_update().execution_options(populate_existing=True))
    if item is None:
        raise HTTPException(status_code=404, detail="resource_not_found")
    # A key is bound to the exact operation and proposal digest. The proposal
    # itself is the replay boundary: once executed, a different key still gets
    # the persisted receipt for that exact version.
    from hashlib import sha256
    key_digest = sha256(payload.idempotency_key.encode()).hexdigest()
    prior_key = db.scalar(select(GlicoExecution).where(
        GlicoExecution.owner_account_id == principal.account.id,
        GlicoExecution.idempotency_digest == key_digest,
    ))
    if prior_key is not None and (
        prior_key.proposal_id != item.id
        or prior_key.proposal_version != payload.version
        or prior_key.request_digest != item.digest
    ):
        raise HTTPException(status_code=409, detail="idempotency_conflict")
    if item.state == "EXECUTED":
        execution = db.scalar(select(GlicoExecution).where(
            GlicoExecution.proposal_id == item.id, GlicoExecution.proposal_version == payload.version)
            .with_for_update())
        if execution and payload.version == item.version and payload.context_version == conversation.context_version:
            return {"receipt": _receipt(execution)}
        raise HTTPException(status_code=409, detail="proposal_version_conflict")
    if item.expires_at <= datetime.utcnow():
        item.state = "EXPIRED"
        item.payload_encrypted = b""
        db.execute(update(GlicoProposalRevision).where(
            GlicoProposalRevision.proposal_id == item.id).values(payload_encrypted=b""))
        db.commit()
        raise HTTPException(status_code=410, detail="proposal_expired")
    if item.state != "READY" or payload.version != item.version or payload.context_version != item.context_version or payload.context_version != conversation.context_version:
        raise HTTPException(status_code=409, detail="proposal_version_conflict")
    patient_id, association_id = active_context(db, principal, item.patient_id)
    if principal.patient is not None and item.association_id is not None:
        selected_link = db.scalar(select(PatientDoctorLink).where(
            PatientDoctorLink.id == item.association_id, PatientDoctorLink.patient_id == item.patient_id,
            PatientDoctorLink.status == "ACTIVE"))
        association_id = selected_link.id if selected_link else None
    if patient_id != item.patient_id or association_id != item.association_id:
        raise HTTPException(status_code=404, detail="resource_not_found")
    fields = proposal_payload(item)["fields"]
    if item.kind in {"investigation_open", "investigation_message"}:
        if not item.association_id:
            raise HTTPException(status_code=409, detail="context_changed")
        link = db.scalar(select(PatientDoctorLink).where(
            PatientDoctorLink.id == item.association_id, PatientDoctorLink.patient_id == item.patient_id,
            PatientDoctorLink.status == "ACTIVE"))
        if link is None:
            raise HTTPException(status_code=404, detail="resource_not_found")
        from app.services.investigations import (InvestigationNotFound, append_message,
            authorized_investigation, open_investigation)
        if item.kind == "investigation_open":
            result = open_investigation(db, principal,
                doctor_id=link.doctor_id if principal.patient else None,
                patient_id=item.patient_id if principal.doctor else None,
                atypical_day_event_id=None, title=fields["title"], initial_message=fields["content"],
                commit=False)
            result_type, result_id = "investigation", result.id
        else:
            investigation_id = fields["investigation_id"]
            try:
                investigation, _, _ = authorized_investigation(db, investigation_id, principal)
            except InvestigationNotFound:
                raise HTTPException(status_code=404, detail="resource_not_found") from None
            if (investigation.patient_id != item.patient_id or investigation.association_id != item.association_id):
                raise HTTPException(status_code=404, detail="resource_not_found")
            result = append_message(db, investigation_id, principal, fields["content"],
                                    payload.idempotency_key, commit=False)
            result_type, result_id = "investigation_message", result.id
        create_execution(db, item, principal, key=payload.idempotency_key,
                         result_type=result_type, result_id=result_id, analytics_status="not_applicable")
        item.state = "EXECUTED"
        item.payload_encrypted = b""
        db.execute(update(GlicoProposalRevision).where(
            GlicoProposalRevision.proposal_id == item.id).values(payload_encrypted=b""))
        db.flush()
        execution = db.scalar(select(GlicoExecution).where(
            GlicoExecution.proposal_id == item.id, GlicoExecution.proposal_version == item.version))
        db.commit()
        return {"receipt": _receipt(execution)}
    if item.kind != "glucose_single":
        raise HTTPException(status_code=422, detail="operation_not_allowed")
    if principal.doctor is not None:
        raise HTTPException(status_code=403, detail="operation_not_allowed")
    try:
        glucose = float(fields["glucose_mg_dl"])
        measured = datetime.fromisoformat(fields["measured_at"])
        if measured.tzinfo is None or not (20 <= glucose <= 600):
            raise ValueError
    except (KeyError, TypeError, ValueError, OverflowError):
        raise HTTPException(status_code=422, detail="invalid_fields")
    patient = db.get(Patient, item.patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="resource_not_found")
    from app.core.patient_time import patient_local_date
    record = create_manual_glucose_record(db, patient, measured, glucose,
        fields.get("context_label"), fields.get("notes"), principal.account.id, commit=False,
        source_type=item.origin if item.origin in {"glico_text", "glico_photo", "glico_audio"} else "glico_text")
    create_execution(db, item, principal, key=payload.idempotency_key,
                     result_type="glucose_record", result_id=record.id,
                     analytics_status="pending")
    item.state = "EXECUTED"
    item.payload_encrypted = b""
    db.execute(update(GlicoProposalRevision).where(
        GlicoProposalRevision.proposal_id == item.id).values(payload_encrypted=b""))
    db.flush()
    execution = db.scalar(select(GlicoExecution).where(
        GlicoExecution.proposal_id == item.id, GlicoExecution.proposal_version == item.version))
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"receipt": _receipt(execution)}


@router.post("/api/glico/proposals/{proposal_id}/cancel")
def cancel_proposal(proposal_id: str, payload: CancelRequest, request: Request,
                    db: Session = Depends(get_db), principal: SessionPrincipal = Depends(require_session)) -> dict:
    _require_glico_enabled()
    _require_csrf(request, principal)
    candidate = db.scalar(select(GlicoProposal).where(
        GlicoProposal.id == proposal_id, GlicoProposal.owner_account_id == principal.account.id))
    if candidate is None:
        raise HTTPException(status_code=404, detail="resource_not_found")
    authorized_conversation(db, candidate.conversation_id, principal, lock=True)
    item = db.scalar(select(GlicoProposal).where(
        GlicoProposal.id == proposal_id, GlicoProposal.owner_account_id == principal.account.id).with_for_update())
    if item is None:
        raise HTTPException(status_code=404, detail="resource_not_found")
    if payload.version != item.version:
        raise HTTPException(status_code=409, detail="proposal_version_conflict")
    if item.state in {"DRAFT", "READY"}:
        item.state = "CANCELLED"
        item.payload_encrypted = b""
        db.execute(update(GlicoProposalRevision).where(
            GlicoProposalRevision.proposal_id == item.id).values(payload_encrypted=b""))
        db.commit()
    return {"id": item.id, "state": item.state, "version": item.version}


@router.get("/api/glico/proposals/{proposal_id}")
def get_proposal(proposal_id: str, db: Session = Depends(get_db),
                 principal: SessionPrincipal = Depends(require_session)) -> dict:
    _require_glico_enabled()
    item = db.scalar(select(GlicoProposal).where(
        GlicoProposal.id == proposal_id, GlicoProposal.owner_account_id == principal.account.id))
    if item is None:
        raise HTTPException(status_code=404, detail="resource_not_found")
    authorized_conversation(db, item.conversation_id, principal)
    if item.state in {"DRAFT", "READY"}:
        return {"proposal": serialize_proposal(item)}
    if item.state == "EXECUTED":
        execution = db.scalar(select(GlicoExecution).where(
            GlicoExecution.proposal_id == item.id, GlicoExecution.proposal_version == item.version))
        return {"receipt": _receipt(execution)} if execution else {"state": "EXECUTED"}
    return {"id": item.id, "state": item.state, "version": item.version}


@router.post("/api/glico/conversations/{conversation_id}/extract/{media_kind}")
async def unavailable_media(conversation_id: str, media_kind: str, request: Request,
                      principal: SessionPrincipal = Depends(require_session), db: Session = Depends(get_db)):
    _require_glico_enabled()
    _require_csrf(request, principal)
    if media_kind not in {"image", "audio"}:
        raise HTTPException(status_code=404, detail="resource_not_found")
    conversation = authorized_conversation(db, conversation_id, principal, lock=True)
    if media_kind == "image" and principal.doctor is not None:
        raise HTTPException(status_code=403, detail="operation_not_allowed")
    try:
        requested_context = int(request.headers.get("x-glico-context-version", ""))
        request_id = request.headers.get("x-glico-request-id", "")
        UUID(request_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="invalid_fields") from None
    if requested_context != conversation.context_version:
        raise HTTPException(status_code=409, detail="context_changed")
    # Freeze the authorization scope before any body read or external work.
    snapshot = (conversation.context_version, conversation.patient_id, conversation.association_id,
                conversation.role, conversation.owner_account_id)
    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/octet-stream":
        raise HTTPException(status_code=415, detail="unsupported_media_type")
    settings = get_settings()
    enabled = settings.glico_photo_enabled if media_kind == "image" else settings.glico_audio_enabled
    if (not enabled or settings.glico_media_global_jobs < 1
            or not settings.glico_media_worker_url
            or not settings.glico_media_worker_secret or len(settings.glico_media_worker_secret.encode()) < 32):
        raise HTTPException(status_code=503, detail="capability_unavailable")
    body_parts: list[bytes] = []
    total = 0
    media_reserved = False
    try:
        async for part in request.stream():
            total += len(part)
            if total > 3 * 1024 * 1024:
                raise HTTPException(status_code=413, detail="payload_too_large")
            body_parts.append(part)
        body = b"".join(body_parts)
        if not body:
            raise HTTPException(status_code=422, detail="invalid_fields")
        body_digest = hashlib.sha256(body).hexdigest()
        cleanup_expired_glico_replays(db)
        replay = _replay_response(db, principal, media_kind, request_id, conversation_id, body_digest)
        if replay is not None:
            return replay
        reserve_media_job(db, principal.account.id, media_kind, settings.glico_media_global_jobs)
        db.commit()
        media_reserved = True
        url = settings.glico_media_worker_url.rstrip("/") + f"/internal/extract/{media_kind}"
        path = f"/internal/extract/{media_kind}"
        timestamp = str(int(time.time()))
        nonce = secrets.token_urlsafe(24)
        correlation = secrets.token_urlsafe(24)
        signed = "\n".join(("POST", path, timestamp, nonce, body_digest)).encode("ascii")
        signature = hmac.new(settings.glico_media_worker_secret.encode(), signed, hashlib.sha256).hexdigest()
        worker_headers = {
            "content-type": "application/octet-stream", "x-correlation-id": correlation,
            "x-worker-timestamp": timestamp, "x-worker-nonce": nonce,
            "x-worker-content-sha256": body_digest, "x-worker-signature": signature,
        }
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(21.0, connect=2.0), follow_redirects=False) as client:
                async with client.stream("POST", url, content=body, headers=worker_headers) as worker_response:
                    response_parts: list[bytes] = []
                    response_size = 0
                    async for part in worker_response.aiter_bytes():
                        response_size += len(part)
                        if response_size > 65536:
                            raise HTTPException(status_code=503, detail="capability_unavailable")
                        response_parts.append(part)
                    worker_status = worker_response.status_code
                    worker_body = b"".join(response_parts)
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="processing_timeout") from None
        except httpx.HTTPError:
            raise HTTPException(status_code=503, detail="capability_unavailable") from None
        if worker_status != 200:
            status = 504 if worker_status == 504 else 413 if worker_status == 413 else 422 if worker_status == 422 else 503
            raise HTTPException(status_code=status, detail="processing_timeout" if status == 504 else "capability_unavailable" if status == 503 else "invalid_fields")
        try:
            import json
            result = json.loads(worker_body)
            trusted_value = _trusted_worker_assessment(result, media_kind)
            if media_kind == "image":
                candidates = result.get("candidates", [])
                extracted_texts = [item["text"] for item in candidates if isinstance(item, dict) and isinstance(item.get("text"), str)]
                recognized_language = None
            else:
                extracted_texts = [result["text"]] if isinstance(result.get("text"), str) else []
                recognized_language = result.get("language")
        except (ValueError, AttributeError, TypeError, KeyError):
            raise HTTPException(status_code=503, detail="capability_unavailable") from None
        # Re-resolve session, account, role, selected patient and link after inference.
        db.expire_all()
        fresh = db.scalar(select(type(principal.session)).where(
            type(principal.session).id == principal.session.id,
            type(principal.session).revoked_at.is_(None), type(principal.session).expires_at > datetime.utcnow()))
        if fresh is None:
            raise HTTPException(status_code=401, detail="authentication_required")
        from app.models.entities import UserAccount
        active_account = db.get(UserAccount, principal.account.id)
        if active_account is None or active_account.account_status != "active":
            raise HTTPException(status_code=401, detail="authentication_required")
        current = authorized_conversation(db, conversation_id, principal)
        if (current.context_version, current.patient_id, current.association_id, current.role,
                current.owner_account_id) != snapshot:
            raise HTTPException(status_code=409, detail="context_changed")
        text = " ".join(extracted_texts).strip()
        answer = None
        proposal_result = None
        llm_proposal = False
        if media_kind == "audio" and text:
            # With the language model on, the transcript is understood like typed text and takes
            # precedence over the keyword matcher; any failure falls back to the matcher.
            spoken_result = None
            if (current.patient_id is not None
                    and getattr(get_settings(), "gemini_api_key", None)):
                try:
                    spoken_result = _language_model_result(db, current, principal, text, [], spoken=True)
                except HTTPException:
                    spoken_result = None
            if spoken_result is not None:
                if spoken_result.get("type") == "proposal":
                    proposal_result, llm_proposal = spoken_result, True
                else:
                    answer = spoken_result
            else:
                answer = _query_answer(db, current, text)
        if media_kind == "image" and any(re.fullmatch(r"\s*(hi|lo)\s*", t, re.I) for t in extracted_texts):
            # Meters print HI/LO outside their measuring range: never a numeric reading.
            answer = {"type": "clarification", "answer_key": "glico.reading.unsupported_signal"}
        if answer is None and media_kind == "audio" and current.patient_id is None:
            answer = {"type": "clarification", "answer_key": "glico.help.try_manual"}
        if (answer is None and trusted_value is not None
                and (media_kind == "image" or len(extracted_texts) == 1)
                and current.patient_id is not None
                and (media_kind == "image" or current.role == "patient")):
            # The worker already isolated the reading; parse that value, not the
            # surrounding OCR text (brand, date, clock), which reads as several values.
            if media_kind == "image":
                proposal_result = _make_proposal(db, current, f"{trusted_value:g} mg/dL")
            else:
                found = result.get("assessment", {}) if isinstance(result, dict) else {}
                original, unit = found.get("candidate_original_value"), found.get("candidate_unit")
                if (unit in {"mg/dL", "mmol/L"} and isinstance(original, (int, float))
                        and not isinstance(original, bool)):
                    proposal_result = _make_proposal(db, current, f"{original:g} {unit}")
                else:
                    proposal_result = _make_proposal(db, current, text)
        if proposal_result and proposal_result.get("type") == "proposal" and not llm_proposal:
            proposal = db.get(GlicoProposal, proposal_result["proposal"]["id"])
            if float(proposal_result["proposal"]["fields"].get("glucose_mg_dl", -1)) != trusted_value:
                db.delete(proposal)
                db.flush()
                proposal_result = None
        if proposal_result and proposal_result.get("type") == "proposal":
            proposal = db.get(GlicoProposal, proposal_result["proposal"]["id"])
            proposal.origin = "glico_photo" if media_kind == "image" else "glico_audio"
            proposal.engine_version = str(result.get("engine", "unknown"))[:120]
            revision = db.scalar(select(GlicoProposalRevision).where(
                GlicoProposalRevision.proposal_id == proposal.id, GlicoProposalRevision.version == proposal.version))
            if revision:
                revision.digest = proposal.digest
            response_data = {"type": "proposal", "proposal": serialize_proposal(proposal)}
        else:
            response_data = answer or {"type": "clarification", "answer_key":
                "glico.reading.ambiguous_image" if media_kind == "image" else "glico.help.try_manual"}
        if media_kind == "audio" and text:
            # Echo what was understood so the user can see it; it is the user's own speech.
            response_data = {**response_data, "transcript": text[:500]}
        _save_replay(db, principal, current, media_kind, request_id, body_digest, response_data)
        db.commit()
        return response_data
    finally:
        if media_reserved:
            try:
                db.rollback()
                release_media_job(db, principal.account.id, media_kind)
                db.commit()
            except Exception:
                db.rollback()
        body_parts.clear()
        if "response_parts" in locals():
            response_parts.clear()
        if "body" in locals():
            del body
        if "worker_body" in locals():
            del worker_body
        if "extracted_texts" in locals():
            extracted_texts.clear()
            del extracted_texts
        if "text" in locals():
            del text
        if "result" in locals():
            del result





