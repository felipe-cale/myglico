"""Registration and credential flows for UserAccount-backed domain roles."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import secrets
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.crypto import (
    crm_uf_lookup,
    decrypt_field,
    email_lookup,
    encrypt_field,
    generate_short_id,
    hash_password,
    normalize_email,
    verify_password,
)
from app.core.security import create_session_record
from app.models.entities import Doctor, Patient, UserAccount, UserSession


_DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(32))


class AuthConflict(Exception):
    """A registration conflicts with an existing unique account/profile."""


class InvalidCredentials(Exception):
    """Generic authentication failure; callers must not reveal which field failed."""


@dataclass(frozen=True)
class RegisteredIdentity:
    account: UserAccount
    patient: Patient | None
    doctor: Doctor | None
    session: UserSession
    session_token: str


def _short_id_for(db: Session, entity_model: type[Patient] | type[Doctor]) -> str:
    return generate_short_id(
        lambda candidate: db.scalar(
            select(entity_model.id).where(entity_model.short_id == candidate).limit(1)
        )
        is not None
    )


def register_account(
    db: Session,
    *,
    role: str,
    email: str,
    password: str,
    display_name: str,
    crm: str | None = None,
    uf: str | None = None,
    privacy_notice_accepted: bool = False,
) -> RegisteredIdentity:
    normalized_email = normalize_email(email)
    display_name = display_name.strip()
    if role not in {"patient", "doctor"}:
        raise ValueError("Unsupported role.")
    if not normalized_email or not display_name:
        raise ValueError("Email and display name are required.")
    if role == "doctor" and (not crm or not crm.strip() or not uf or not uf.strip()):
        raise ValueError("Doctor registration requires CRM and UF.")
    if not privacy_notice_accepted:
        raise ValueError("Registration requires privacy_notice_accepted=true.")
    if (crm is None) != (uf is None):
        raise ValueError("CRM and UF must be supplied together.")
    crm = crm.strip() if crm is not None else None
    uf = uf.strip().upper() if uf is not None else None
    if crm == "":
        crm = None
    if uf == "":
        uf = None
    if (crm is None) != (uf is None):
        raise ValueError("CRM and UF must be supplied together.")

    lookup = email_lookup(normalized_email)
    if db.scalar(select(UserAccount.id).where(UserAccount.email_lookup == lookup).limit(1)):
        raise AuthConflict("Account could not be created.")
    doctor_lookup = crm_uf_lookup(crm, uf) if crm is not None and uf is not None else None
    if doctor_lookup and db.scalar(select(Doctor.id).where(Doctor.crm_uf_lookup == doctor_lookup).limit(1)):
        raise AuthConflict("Account could not be created.")

    password_hash = hash_password(password)
    for attempt in range(5):
        try:
            account = UserAccount(
                email=normalized_email,
                password_hash=password_hash,
                account_status="active",
                email_verified_at=None,
                is_demo=False,
                privacy_notice_accepted_at=datetime.utcnow(),
            )
            db.add(account)
            db.flush()

            patient: Patient | None = None
            doctor: Doctor | None = None
            if role == "patient":
                patient = Patient(name=display_name, user_account=account, short_id=_short_id_for(db, Patient))
                db.add(patient)
            else:
                doctor_id = str(uuid.uuid4())
                doctor = Doctor(
                    id=doctor_id,
                    short_id=_short_id_for(db, Doctor),
                    user_account=account,
                    name_encrypted=encrypt_field(
                        display_name, table="doctors", column="name", record_id=doctor_id
                    ),
                    crm_encrypted=encrypt_field(crm, table="doctors", column="crm", record_id=doctor_id),
                    uf_encrypted=encrypt_field(uf, table="doctors", column="uf", record_id=doctor_id),
                    crm_uf_lookup=doctor_lookup,
                    is_demo=False,
                    declared_verified=False,
                )
                db.add(doctor)

            session, token = create_session_record(db, account.id)
            db.commit()
            db.refresh(account)
            if patient is not None:
                db.refresh(patient)
            if doctor is not None:
                db.refresh(doctor)
            db.refresh(session)
            return RegisteredIdentity(account, patient, doctor, session, token)
        except IntegrityError as exc:
            db.rollback()
            email_exists = db.scalar(select(UserAccount.id).where(UserAccount.email_lookup == lookup).limit(1))
            crm_exists = (
                db.scalar(select(Doctor.id).where(Doctor.crm_uf_lookup == doctor_lookup).limit(1))
                if doctor_lookup
                else None
            )
            if email_exists or crm_exists:
                raise AuthConflict("Account could not be created.") from exc
            if attempt == 4:
                raise AuthConflict("Account could not be created.") from exc
        except Exception:
            db.rollback()
            raise
    raise AuthConflict("Account could not be created.")


def login_account(db: Session, *, email: str, password: str) -> RegisteredIdentity:
    lookup = email_lookup(normalize_email(email))
    account = db.scalar(select(UserAccount).where(UserAccount.email_lookup == lookup))
    password_valid = verify_password(password, account.password_hash if account is not None else _DUMMY_PASSWORD_HASH)
    if account is None or account.account_status != "active" or not password_valid:
        raise InvalidCredentials("Invalid email or password.")

    patient = db.scalar(select(Patient).where(Patient.user_account_id == account.id))
    doctor = db.scalar(select(Doctor).where(Doctor.user_account_id == account.id))
    if (patient is None and doctor is None) or (patient is not None and doctor is not None):
        raise InvalidCredentials("Invalid email or password.")
    try:
        session, token = create_session_record(db, account.id)
        db.commit()
        db.refresh(session)
        return RegisteredIdentity(account, patient, doctor, session, token)
    except Exception:
        db.rollback()
        raise


def revoke_session(db: Session, token: str | None) -> None:
    if not token or len(token) > 64:
        return
    session = db.get(UserSession, token)
    if session is not None and session.revoked_at is None:
        from datetime import datetime

        session.revoked_at = datetime.utcnow()
        db.commit()


def patient_payload(patient: Patient) -> dict[str, object]:
    return {"id": patient.id, "short_id": patient.short_id, "display_name": patient.display_name}


def doctor_payload(doctor: Doctor) -> dict[str, object]:
    return {
        "id": doctor.id,
        "short_id": doctor.short_id,
        "name": decrypt_field(doctor.name_encrypted, table="doctors", column="name", record_id=doctor.id),
        "crm": decrypt_field(doctor.crm_encrypted, table="doctors", column="crm", record_id=doctor.id),
        "uf": decrypt_field(doctor.uf_encrypted, table="doctors", column="uf", record_id=doctor.id),
        "is_demo": doctor.is_demo,
        "declared_verified": doctor.declared_verified,
    }
