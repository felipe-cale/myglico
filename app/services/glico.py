from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import hmac
import json
import secrets
from typing import Any
from uuid import uuid4
from urllib.parse import urlsplit

from fastapi import HTTPException, Request
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.crypto import decrypt_field, encrypt_field
from app.core.security import SessionPrincipal
from app.models.entities import PatientDoctorLink, UserAccount
from app.models.glico import (GlicoConversation, GlicoExecution, GlicoGlobalQuota, GlicoProposal,
                              GlicoProposalRevision, GlicoQuotaBucket, GlicoRequestReplay)

LOCALES = {"pt-BR", "en-US", "es"}
TERMINAL = {"EXECUTED", "CANCELLED", "EXPIRED", "INVALIDATED"}


def _digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def csrf_token(session_token: str) -> str:
    key = get_settings().lookup_hmac_key
    if not key:
        raise RuntimeError("MYGLICO_LOOKUP_HMAC_KEY is required")
    return hmac.new(bytes.fromhex(key), ("glico-csrf:" + session_token).encode(), hashlib.sha256).hexdigest()


def require_csrf(request: Request, principal: SessionPrincipal) -> None:
    supplied = request.headers.get("x-myglico-csrf", "")
    cookie = request.cookies.get("myglico_session", "")
    origin = request.headers.get("origin")
    referer = request.headers.get("referer")
    source = origin or referer
    expected = urlsplit(str(request.base_url))
    actual = urlsplit(source or "")
    same_origin = (actual.scheme in {"https", "http"}
                   and actual.scheme == expected.scheme
                   and actual.netloc.lower() == expected.netloc.lower())
    if not same_origin or not secrets.compare_digest(supplied, csrf_token(cookie)):
        raise HTTPException(status_code=403, detail="csrf_failed")
    if principal.session.id != cookie:
        raise HTTPException(status_code=401, detail="authentication_required")


def active_context(db: Session, principal: SessionPrincipal, patient_id: str | None) -> tuple[str, str | None]:
    if principal.patient is not None:
        if patient_id is not None and patient_id != principal.patient.id:
            raise HTTPException(status_code=404, detail="resource_not_found")
        return principal.patient.id, None
    if principal.doctor is None or not patient_id:
        raise HTTPException(status_code=422, detail="invalid_fields")
    link = db.scalar(select(PatientDoctorLink).where(
        PatientDoctorLink.patient_id == patient_id,
        PatientDoctorLink.doctor_id == principal.doctor.id,
        PatientDoctorLink.status == "ACTIVE",
    ).with_for_update())
    if link is None:
        raise HTTPException(status_code=404, detail="resource_not_found")
    return patient_id, link.id


def authorized_conversation(db: Session, conversation_id: str, principal: SessionPrincipal,
                           *, lock: bool = False) -> GlicoConversation:
    query = select(GlicoConversation).where(
        GlicoConversation.id == conversation_id,
        GlicoConversation.owner_account_id == principal.account.id,
        GlicoConversation.expires_at > datetime.utcnow(),
    )
    if lock:
        query = query.with_for_update()
    item = db.scalar(query)
    if item is None:
        raise HTTPException(status_code=404, detail="resource_not_found")
    if item.patient_id is None and principal.doctor is not None:
        return item
    if item.patient_id is None:
        raise HTTPException(status_code=404, detail="resource_not_found")
    patient_id, association_id = active_context(db, principal, item.patient_id)
    if item.role == "patient" and item.association_id:
        link = db.scalar(select(PatientDoctorLink).where(
            PatientDoctorLink.id == item.association_id,
            PatientDoctorLink.patient_id == patient_id,
            PatientDoctorLink.status == "ACTIVE",
        ))
        if link is None:
            raise HTTPException(status_code=404, detail="resource_not_found")
        association_id = link.id
    if item.role == "doctor" and association_id != item.association_id:
        raise HTTPException(status_code=404, detail="resource_not_found")
    if patient_id != item.patient_id:
        raise HTTPException(status_code=404, detail="resource_not_found")
    return item


def invalidate_proposals(db: Session, conversation_id: str) -> None:
    ids = db.scalars(select(GlicoProposal.id).where(
        GlicoProposal.conversation_id == conversation_id,
        GlicoProposal.state.in_(("DRAFT", "READY")),
    )).all()
    if not ids:
        return
    db.execute(update(GlicoProposal).where(
        GlicoProposal.id.in_(ids),
    ).values(state="INVALIDATED", payload_encrypted=b"", updated_at=datetime.utcnow()))
    db.execute(update(GlicoProposalRevision).where(GlicoProposalRevision.proposal_id.in_(ids))
               .values(payload_encrypted=b""))


def proposal_payload(proposal: GlicoProposal) -> dict[str, Any]:
    raw = decrypt_field(proposal.payload_encrypted, table="glico_proposals", column="payload", record_id=proposal.id)
    return json.loads(raw or "{}")


def create_proposal(db: Session, conversation: GlicoConversation, *, kind: str, fields: dict[str, Any], origin: str, ready: bool) -> GlicoProposal:
    now = datetime.utcnow()
    db.execute(update(UserAccount).where(UserAccount.id == conversation.owner_account_id)
               .values(account_status=UserAccount.account_status))
    live = db.scalar(select(func.count()).select_from(GlicoProposal).where(
        GlicoProposal.owner_account_id == conversation.owner_account_id,
        GlicoProposal.state.in_(("DRAFT", "READY")), GlicoProposal.expires_at > now,
    )) or 0
    if live >= 10:
        raise HTTPException(status_code=429, detail="quota_exceeded", headers={"Retry-After": "60"})
    proposal_id = str(uuid4())
    body = {"fields": fields, "missing_fields": [], "warnings": []}
    expires = min(conversation.expires_at, now + timedelta(minutes=15))
    ciphertext = encrypt_field(json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False), table="glico_proposals", column="payload", record_id=proposal_id)
    item = GlicoProposal(
        id=proposal_id, conversation_id=conversation.id, owner_account_id=conversation.owner_account_id,
        patient_id=conversation.patient_id, association_id=conversation.association_id,
        kind=kind, version=1, context_version=conversation.context_version,
        state="READY" if ready else "DRAFT", payload_encrypted=ciphertext,
        digest=_digest({"kind": kind, "fields": fields, "patient": conversation.patient_id,
                        "association": conversation.association_id, "owner": conversation.owner_account_id,
                        "version": 1, "context_version": conversation.context_version, "normalizer": 1}),
        origin=origin, expires_at=expires,
    )
    db.add(item)
    db.flush()
    db.add(GlicoProposalRevision(proposal_id=item.id, version=1, context_version=item.context_version,
        payload_encrypted=ciphertext, digest=item.digest))
    db.flush()
    return item


def serialize_proposal(item: GlicoProposal) -> dict[str, Any]:
    payload = proposal_payload(item)
    return {"id": item.id, "kind": item.kind, "version": item.version,
            "context_version": item.context_version, "state": item.state,
            "expires_at": item.expires_at.isoformat() + "Z", "fields": payload.get("fields", {}),
            "missing_fields": payload.get("missing_fields", []), "warnings": payload.get("warnings", []),
            "origin": item.origin}


def consume_quota(db: Session, owner_id: str, bucket_name: str, limit: int, *, window_seconds: int = 60) -> None:
    now = datetime.utcnow()
    # Row write serializes quota increments across workers, including SQLite
    # where SELECT FOR UPDATE does not acquire a lock.
    db.execute(update(UserAccount).where(UserAccount.id == owner_id)
               .values(account_status=UserAccount.account_status))
    epoch = int(now.timestamp())
    start = datetime.utcfromtimestamp(epoch - epoch % window_seconds)
    bucket = db.scalar(select(GlicoQuotaBucket).where(
        GlicoQuotaBucket.owner_account_id == owner_id, GlicoQuotaBucket.bucket == bucket_name,
        GlicoQuotaBucket.window_start == start,
    ).with_for_update())
    if bucket is None:
        try:
            with db.begin_nested():
                bucket = GlicoQuotaBucket(owner_account_id=owner_id, bucket=bucket_name,
                                          window_start=start, used=0, reserved=0)
                db.add(bucket)
                db.flush()
        except IntegrityError:
            bucket = db.scalar(select(GlicoQuotaBucket).where(
                GlicoQuotaBucket.owner_account_id == owner_id, GlicoQuotaBucket.bucket == bucket_name,
                GlicoQuotaBucket.window_start == start,
            ).with_for_update())
        if bucket is None:
            raise HTTPException(status_code=503, detail="capability_unavailable")
    if bucket.used + bucket.reserved >= limit:
        retry = max(1, int((start + timedelta(seconds=window_seconds) - now).total_seconds()))
        raise HTTPException(status_code=429, detail="quota_exceeded", headers={"Retry-After": str(retry)})
    bucket.used += 1


def reserve_media_job(db: Session, owner_id: str, media_kind: str, global_limit: int,
                      daily_limit: int | None = None) -> None:
    """Charge the shared daily allowance and atomically enforce one live job per account."""
    if global_limit < 1:
        raise HTTPException(status_code=503, detail="capability_unavailable")
    db.execute(update(GlicoGlobalQuota).where(GlicoGlobalQuota.bucket == media_kind)
               .values(reserved=GlicoGlobalQuota.reserved))
    global_row = db.scalar(select(GlicoGlobalQuota).where(GlicoGlobalQuota.bucket == media_kind)
                           .with_for_update())
    if global_row is None:
        raise HTTPException(status_code=503, detail="capability_unavailable")
    if global_row.reserved >= global_limit:
        raise HTTPException(status_code=429, detail="quota_exceeded", headers={"Retry-After": "5"})
    global_row.reserved += 1
    if daily_limit is None:
        daily_limit = 20 if media_kind == "image" else 30
    if daily_limit > 0:  # 0 = no per-account limit (local testing)
        consume_quota(db, owner_id, f"glico_{media_kind}_day", daily_limit, window_seconds=86400)
    marker = datetime(2000, 1, 1)
    active = db.scalar(select(GlicoQuotaBucket).where(
        GlicoQuotaBucket.owner_account_id == owner_id,
        GlicoQuotaBucket.bucket == f"{media_kind}_active", GlicoQuotaBucket.window_start == marker,
    ).with_for_update())
    if active is None:
        active = GlicoQuotaBucket(owner_account_id=owner_id, bucket=f"{media_kind}_active",
                                  window_start=marker, used=0, reserved=0)
        db.add(active)
        db.flush()
    if active.reserved >= 1:
        raise HTTPException(status_code=429, detail="quota_exceeded", headers={"Retry-After": "5"})
    active.reserved += 1


def release_media_job(db: Session, owner_id: str, media_kind: str) -> None:
    db.execute(update(GlicoGlobalQuota).where(GlicoGlobalQuota.bucket == media_kind)
               .values(reserved=GlicoGlobalQuota.reserved))
    global_row = db.get(GlicoGlobalQuota, media_kind)
    if global_row is not None and global_row.reserved > 0:
        global_row.reserved -= 1
    marker = datetime(2000, 1, 1)
    active = db.scalar(select(GlicoQuotaBucket).where(
        GlicoQuotaBucket.owner_account_id == owner_id,
        GlicoQuotaBucket.bucket == f"{media_kind}_active", GlicoQuotaBucket.window_start == marker,
    ).with_for_update())
    if active is not None and active.reserved > 0:
        active.reserved -= 1


def cleanup_expired_glico_replays(db: Session, *, now: datetime | None = None) -> int:
    """Delete expired idempotency responses so their keys and storage can be reused."""
    result = db.execute(delete(GlicoRequestReplay).where(
        GlicoRequestReplay.expires_at <= (now or datetime.utcnow())))
    return int(result.rowcount or 0)


def create_execution(db: Session, proposal: GlicoProposal, principal: SessionPrincipal, *, key: str, result_type: str, result_id: str | None, analytics_status: str) -> GlicoExecution:
    key_digest = hashlib.sha256(key.encode()).hexdigest()
    execution = GlicoExecution(
        proposal_id=proposal.id, proposal_version=proposal.version, owner_account_id=principal.account.id,
        operation=proposal.kind, idempotency_digest=key_digest, request_digest=proposal.digest,
        result_type=result_type, result_id=result_id, analytics_status=analytics_status,
    )
    db.add(execution)
    return execution







