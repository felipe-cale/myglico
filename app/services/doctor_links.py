"""Transactional patient-doctor association lifecycle and notifications."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.crypto import encrypt_field
from app.models.entities import Doctor, Notification, NotificationOutbox, Patient, PatientDoctorLink, ProvenanceEvent
from app.core.security import SessionPrincipal


class LinkConflict(Exception):
    pass


class LinkNotFound(Exception):
    pass


def _now() -> datetime:
    return datetime.utcnow()


def _doctor_account(db: Session, doctor: Doctor) -> str:
    return doctor.user_account_id


def _patient_account(db: Session, patient: Patient) -> str:
    if patient.user_account_id is None:
        raise LinkConflict("Patient has no account")
    return patient.user_account_id


def _event(
    *, link: PatientDoctorLink, activity: str, principal: SessionPrincipal,
    from_status: str | None, to_status: str, before_version: int, after_version: int,
) -> ProvenanceEvent:
    event = ProvenanceEvent(
        id=str(uuid4()),
        activity_type=activity,
        entity_type="patient_doctor_link",
        entity_id=link.id,
        actor_user_id=principal.account.id,
        source_type="user",
        source_id=principal.patient.id if principal.patient else principal.doctor.id if principal.doctor else None,
        occurred_at=_now(),
        prov_json={"activity": activity, "aggregate_version": after_version},
        metadata_json={
            "patient_id": link.patient_id,
            "doctor_id": link.doctor_id,
            "from_status": from_status,
            "to_status": to_status,
            "before_version": before_version,
            "after_version": after_version,
        },
    )
    return event


def _commit_transition(
    db: Session, link: PatientDoctorLink, event: ProvenanceEvent,
    recipient_account_id: str | None, notification_type: str | None,
    notification_payload: dict | None,
) -> None:
    db.add(event)
    if recipient_account_id and notification_type and notification_payload is not None:
        notification = Notification(
            id=str(uuid4()),
            recipient_user_account_id=recipient_account_id,
            notification_type=notification_type,
            payload=notification_payload,
            causation_event_id=event.id,
        )
        db.add(notification)
        db.add(NotificationOutbox(notification_id=notification.id))
        db.add(ProvenanceEvent(
            activity_type="NotificationCreated", entity_type="notification", entity_id=notification.id,
            actor_user_id=None, source_type="software-agent", source_id=event.id,
            occurred_at=_now(), prov_json={"activity": "NotificationCreated"},
            metadata_json={"recipient_user_account_id": recipient_account_id,
                          "notification_type": notification_type, "causation_event_id": event.id},
        ))
    try:
        if event.activity_type == "AssociationRevoked":
            from app.services.investigations import close_for_revoked_association

            close_for_revoked_association(db, link, event)
        db.commit()
        db.refresh(link)
    except Exception:
        db.rollback()
        raise


def request_link(db: Session, principal: SessionPrincipal, doctor_short_id: str) -> tuple[PatientDoctorLink, bool]:
    patient = principal.patient
    if patient is None:
        raise PermissionError
    doctor = db.scalar(select(Doctor).where(Doctor.short_id == doctor_short_id.strip().upper()))
    if doctor is None:
        raise LinkNotFound
    if principal.doctor is not None and principal.doctor.id == doctor.id:
        raise PermissionError
    existing = db.scalar(select(PatientDoctorLink).where(
        PatientDoctorLink.patient_id == patient.id,
        PatientDoctorLink.doctor_id == doctor.id,
        PatientDoctorLink.status.in_(("PENDING", "ACTIVE")),
    ))
    if existing is not None:
        if existing.status == "PENDING":
            return existing, False
        raise LinkConflict("An active link already exists")

    link = PatientDoctorLink(
        id=str(uuid4()), patient_id=patient.id, doctor_id=doctor.id,
        status="PENDING", version=1, open_pair_key="open",
    )
    db.add(link)
    event = _event(link=link, activity="AssociationRequested", principal=principal,
                   from_status=None, to_status="PENDING", before_version=0, after_version=1)
    db.add(event)
    notification = Notification(
        id=str(uuid4()),
        recipient_user_account_id=_doctor_account(db, doctor),
        notification_type="association_requested",
        payload={"link_id": link.id, "patient_short_id": patient.short_id},
        causation_event_id=event.id,
    )
    db.add(notification)
    db.add(NotificationOutbox(notification_id=notification.id))
    db.add(ProvenanceEvent(
        activity_type="NotificationCreated", entity_type="notification", entity_id=notification.id,
        actor_user_id=None, source_type="software-agent", source_id=event.id,
        occurred_at=_now(), prov_json={"activity": "NotificationCreated"},
        metadata_json={"recipient_user_account_id": doctor.user_account_id,
                      "notification_type": "association_requested", "causation_event_id": event.id},
    ))
    try:
        db.commit()
        db.refresh(link)
        return link, True
    except IntegrityError:
        db.rollback()
        current = db.scalar(select(PatientDoctorLink).where(
            PatientDoctorLink.patient_id == patient.id,
            PatientDoctorLink.doctor_id == doctor.id,
            PatientDoctorLink.status.in_(("PENDING", "ACTIVE")),
        ))
        if current is not None and current.status == "PENDING":
            return current, False
        raise
    except Exception:
        db.rollback()
        raise


def _get_participant_link(db: Session, link_id: str, principal: SessionPrincipal) -> PatientDoctorLink:
    link = db.get(PatientDoctorLink, link_id)
    if link is None:
        raise LinkNotFound
    is_patient = principal.patient is not None and link.patient_id == principal.patient.id
    is_doctor = principal.doctor is not None and link.doctor_id == principal.doctor.id
    if not (is_patient or is_doctor):
        raise LinkNotFound
    return link


def transition_link(
    db: Session, link_id: str, principal: SessionPrincipal, action: str,
    expected_version: int, reason: str | None = None,
) -> PatientDoctorLink:
    link = _get_participant_link(db, link_id, principal)
    is_patient = principal.patient is not None and link.patient_id == principal.patient.id
    is_doctor = principal.doctor is not None and link.doctor_id == principal.doctor.id
    if action in ("confirm", "reject") and (not is_doctor or is_patient):
        raise PermissionError
    if action == "cancel" and not is_patient:
        raise PermissionError
    if action == "revoke" and not (is_patient or is_doctor):
        raise PermissionError

    target = {"confirm": "ACTIVE", "reject": "REJECTED", "cancel": "CANCELLED", "revoke": "REVOKED"}[action]
    if link.status == target and action in ("confirm", "reject"):
        return link  # Idempotent retry; it must not create a second event.
    expected_state = "PENDING" if action in ("confirm", "reject", "cancel") else "ACTIVE"
    if link.status != expected_state:
        raise LinkConflict(f"Cannot {action} a {link.status.lower()} association")
    if link.version != expected_version:
        raise LinkConflict("Association version is stale")

    before_version = link.version
    now = _now()
    values: dict[str, object] = {
        "status": target, "version": before_version + 1,
        "open_pair_key": None,
    }
    if action in ("confirm", "reject", "cancel"):
        values["decided_at"] = now
    if action == "revoke":
        values.update(revoked_at=now, revoked_by_role="patient" if is_patient else "doctor")
        if reason:
            values["reason_encrypted"] = encrypt_field(reason, table="patient_doctor_links", column="reason", record_id=link.id)

    updated = db.execute(update(PatientDoctorLink).where(
        PatientDoctorLink.id == link.id,
        PatientDoctorLink.version == expected_version,
        PatientDoctorLink.status == expected_state,
    ).values(**values).execution_options(synchronize_session=False))
    if updated.rowcount != 1:
        db.rollback()
        current = db.get(PatientDoctorLink, link_id)
        if current is not None and current.status == target and action in ("confirm", "reject"):
            return current
        raise LinkConflict("Association changed concurrently; reload and retry")
    db.expire(link)
    db.refresh(link)
    activity = {
        "confirm": "AssociationConfirmed", "reject": "AssociationRejected",
        "cancel": "AssociationRequestCancelled", "revoke": "AssociationRevoked",
    }[action]
    event = _event(link=link, activity=activity, principal=principal,
                   from_status=expected_state, to_status=target,
                   before_version=before_version, after_version=before_version + 1)
    recipient_id = _patient_account(db, link.patient) if action in ("confirm", "reject") else _doctor_account(db, link.doctor) if action == "cancel" else (
        _doctor_account(db, link.doctor) if is_patient else _patient_account(db, link.patient)
    )
    notification_type = {
        "confirm": "association_confirmed", "reject": "association_rejected",
        "cancel": "association_cancelled", "revoke": "association_revoked",
    }[action]
    payload = {"link_id": link.id, "status": target.lower()}
    if action == "revoke":
        payload["revoked_by_role"] = "patient" if is_patient else "doctor"
    _commit_transition(db, link, event, recipient_id, notification_type, payload)
    return link


def list_links(db: Session, principal: SessionPrincipal) -> list[PatientDoctorLink]:
    if principal.patient is not None:
        return list(db.scalars(select(PatientDoctorLink).where(
            PatientDoctorLink.patient_id == principal.patient.id
        ).order_by(PatientDoctorLink.requested_at.desc())))
    if principal.doctor is not None:
        return list(db.scalars(select(PatientDoctorLink).where(
            PatientDoctorLink.doctor_id == principal.doctor.id
        ).order_by(PatientDoctorLink.requested_at.desc())))
    return []


def notification_list(db: Session, account_id: str, unread_only: bool = False) -> tuple[list[Notification], int]:
    query = select(Notification).where(Notification.recipient_user_account_id == account_id)
    count = db.scalar(select(func.count(Notification.id)).where(
        Notification.recipient_user_account_id == account_id, Notification.read_at.is_(None)
    )) or 0
    if unread_only:
        query = query.where(Notification.read_at.is_(None))
    return list(db.scalars(query.order_by(Notification.created_at.desc()))), count
