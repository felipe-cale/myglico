"""Server-side, revocable browser sessions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import secrets

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models.entities import Doctor, Patient, UserAccount, UserSession


SESSION_COOKIE_NAME = "myglico_session"


@dataclass(frozen=True)
class SessionPrincipal:
    session: UserSession
    account: UserAccount
    patient: Patient | None
    doctor: Doctor | None


def new_session_id() -> str:
    """Return an unguessable, URL-safe session identifier from the OS CSPRNG."""
    return secrets.token_urlsafe(32)


def create_session_record(db: Session, account_id: str) -> tuple[UserSession, str]:
    token = new_session_id()
    expires_at = datetime.utcnow() + timedelta(hours=get_settings().session_ttl_hours)
    record = UserSession(id=token, user_account_id=account_id, expires_at=expires_at)
    db.add(record)
    db.flush()
    return record, token


def set_session_cookie(response: Response, token: str, expires_at: datetime) -> None:
    max_age = max(0, int((expires_at - datetime.utcnow()).total_seconds()))
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=max_age,
        expires=max_age,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )


def resolve_session(request: Request, db: Session) -> SessionPrincipal | None:
    """Resolve account roles from current database state for this request."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token or len(token) > 64:
        return None
    now = datetime.utcnow()
    session = db.scalar(
        select(UserSession).where(
            UserSession.id == token,
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > now,
        )
    )
    if session is None:
        return None
    account = db.get(UserAccount, session.user_account_id)
    if account is None or account.account_status != "active":
        return None
    patient = db.scalar(select(Patient).where(Patient.user_account_id == account.id))
    doctor = db.scalar(select(Doctor).where(Doctor.user_account_id == account.id))
    if (patient is None and doctor is None) or (patient is not None and doctor is not None):
        return None
    return SessionPrincipal(session=session, account=account, patient=patient, doctor=doctor)


def require_session(
    request: Request,
    db: Session = Depends(get_db),
) -> SessionPrincipal:
    principal = resolve_session(request, db)
    if principal is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return principal
