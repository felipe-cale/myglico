"""Authorized, encrypted CSCW investigations and atypical-day prompts."""

from __future__ import annotations

from datetime import date, datetime
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.crypto import decrypt_field, encrypt_field
from app.core.security import SessionPrincipal
from app.models.entities import (
    AtypicalDayPrompt, DailyIndicator, Doctor, Investigation, InvestigationAtypicalDay, InvestigationMessage,
    InvestigationReadPosition, Notification, NotificationOutbox, Patient, PatientDoctorLink, ProvenanceEvent,
)


class InvestigationNotFound(Exception):
    pass


class InvestigationConflict(Exception):
    pass


def _now() -> datetime:
    return datetime.utcnow()


def _actor(principal: SessionPrincipal) -> tuple[str, str]:
    if principal.patient is not None:
        return "PATIENT", principal.patient.id
    if principal.doctor is not None:
        return "DOCTOR", principal.doctor.id
    raise PermissionError


def _activity_event(
    activity: str, investigation: Investigation, principal: SessionPrincipal | None,
    metadata: dict, *, causation_id: str | None = None,
) -> ProvenanceEvent:
    role, domain_id = _actor(principal) if principal is not None else ("SYSTEM", "")
    return ProvenanceEvent(
        id=str(uuid4()), activity_type=activity, entity_type="investigation",
        entity_id=investigation.id, actor_user_id=principal.account.id if principal else None,
        source_type="user" if principal else "software-agent", source_id=domain_id or causation_id,
        occurred_at=_now(), prov_json={"activity": activity},
        metadata_json={**metadata, "actor_role": role, "causation_event_id": causation_id},
    )


def _add_notification(
    db: Session, *, recipient_id: str | None, notification_type: str,
    payload: dict, cause_event: ProvenanceEvent,
) -> None:
    if not recipient_id:
        return
    notification = Notification(
        id=str(uuid4()), recipient_user_account_id=recipient_id,
        notification_type=notification_type, payload=payload,
        causation_event_id=cause_event.id,
    )
    db.add(notification)
    db.add(NotificationOutbox(notification_id=notification.id))
    db.add(ProvenanceEvent(
        id=str(uuid4()), activity_type="NotificationCreated", entity_type="notification",
        entity_id=notification.id, actor_user_id=None, source_type="software-agent",
        source_id=cause_event.id, occurred_at=_now(), prov_json={"activity": "NotificationCreated"},
        metadata_json={"recipient_user_account_id": recipient_id,
                       "notification_type": notification_type,
                       "causation_event_id": cause_event.id},
    ))


def _counterpart_account(db: Session, investigation: Investigation, role: str) -> str | None:
    if role == "PATIENT":
        return db.scalar(select(Patient.user_account_id).where(Patient.id == investigation.patient_id))
    return db.scalar(select(Doctor.user_account_id).where(Doctor.id == investigation.doctor_id))


def _lock_active_association(db: Session, investigation: Investigation) -> None:
    # The no-op update obtains a database write lock in the same lock order as
    # B3 revocation, serializing message writes against association revocation.
    result = db.execute(update(PatientDoctorLink).where(
        PatientDoctorLink.id == investigation.association_id,
        PatientDoctorLink.patient_id == investigation.patient_id,
        PatientDoctorLink.doctor_id == investigation.doctor_id,
        PatientDoctorLink.status == "ACTIVE",
    ).values(status="ACTIVE").execution_options(synchronize_session=False))
    if result.rowcount != 1:
        raise InvestigationConflict("The association is no longer active")


def _participant(
    db: Session, investigation: Investigation, principal: SessionPrincipal,
    *, doctor_requires_active_link: bool = True,
) -> tuple[str, str]:
    role, domain_id = _actor(principal)
    if role == "PATIENT" and domain_id == investigation.patient_id:
        return role, domain_id
    if role == "DOCTOR" and domain_id == investigation.doctor_id:
        if doctor_requires_active_link:
            try:
                _lock_active_association(db, investigation)
            except InvestigationConflict as exc:
                # A revoked doctor must not learn that the conversation exists.
                raise InvestigationNotFound from exc
        return role, domain_id
    raise InvestigationNotFound


def open_investigation(
    db: Session, principal: SessionPrincipal, *, doctor_id: str | None,
    patient_id: str | None, atypical_day_event_id: str | None,
    title: str, initial_message: str, atypical_day_event_ids: list[str] | None = None,
) -> Investigation:
    role, domain_id = _actor(principal)
    if role == "PATIENT":
        if not doctor_id or patient_id is not None:
            raise ValueError("Patients must select exactly one doctor_id")
        target_patient_id, target_doctor_id = domain_id, doctor_id
    else:
        if not patient_id or doctor_id is not None:
            raise ValueError("Doctors must select exactly one patient_id")
        target_patient_id, target_doctor_id = patient_id, domain_id
    if not title.strip() or not initial_message.strip():
        raise ValueError("Title and initial message are required")
    if len(title) > 180 or len(initial_message) > 10000:
        raise ValueError("Title or message exceeds the allowed length")

    association = db.scalar(select(PatientDoctorLink).where(
        PatientDoctorLink.patient_id == target_patient_id,
        PatientDoctorLink.doctor_id == target_doctor_id,
        PatientDoctorLink.status == "ACTIVE",
    ))
    if association is None:
        raise InvestigationNotFound
    # Lock the exact authorization cycle before writing the aggregate.
    lock_result = db.execute(update(PatientDoctorLink).where(
        PatientDoctorLink.id == association.id, PatientDoctorLink.status == "ACTIVE",
    ).values(status="ACTIVE").execution_options(synchronize_session=False))
    if lock_result.rowcount != 1:
        raise InvestigationConflict("The association is no longer active")

    requested_ids = list(dict.fromkeys([*(atypical_day_event_ids or []), *([atypical_day_event_id] if atypical_day_event_id else [])]))
    indicators = [db.get(DailyIndicator, indicator_id) for indicator_id in requested_ids]
    if any(indicator is None or indicator.patient_id != target_patient_id or not indicator.anomaly_flag for indicator in indicators):
        raise InvestigationNotFound
    indicators = sorted(indicators, key=lambda indicator: (indicator.indicator_date, indicator.id))
    primary_indicator_id = indicators[0].id if indicators else None

    investigation_id = str(uuid4())
    investigation = Investigation(
        id=investigation_id, patient_id=target_patient_id, doctor_id=target_doctor_id,
        association_id=association.id, atypical_day_event_id=primary_indicator_id,
        title_encrypted=encrypt_field(title.strip(), table="investigations", column="title", record_id=investigation_id),
        status="OPEN", awaiting_role="DOCTOR" if role == "PATIENT" else "PATIENT",
        opened_by_role=role, opened_by_domain_id=domain_id, opened_at=_now(), version=1,
    )
    investigation.atypical_days = [InvestigationAtypicalDay(
        daily_indicator_id=indicator.id, indicator_date=indicator.indicator_date,
    ) for indicator in indicators]
    message_id = str(uuid4())
    message = InvestigationMessage(
        id=message_id, investigation_id=investigation_id, author_role=role,
        author_domain_id=domain_id,
        content_encrypted=encrypt_field(initial_message.strip(), table="investigation_messages", column="content", record_id=message_id),
        sequence=1, created_at=_now(),
    )
    db.add_all([investigation, message])
    opened_event = _activity_event("InvestigationOpened", investigation, principal, {
        "patient_id": target_patient_id, "doctor_id": target_doctor_id,
        "association_id": association.id, "atypical_day_event_id": primary_indicator_id,
        "atypical_day_event_ids": [indicator.id for indicator in indicators],
        "opened_by_role": role, "version": 1,
    })
    message_event = _activity_event("InvestigationMessageAdded", investigation, principal, {
        "message_id": message_id, "sequence": 1, "author_role": role,
    }, causation_id=opened_event.id)
    db.add_all([opened_event, message_event])
    counterpart_role = "DOCTOR" if role == "PATIENT" else "PATIENT"
    _add_notification(
        db, recipient_id=_counterpart_account(db, investigation, counterpart_role),
        notification_type="investigation_opened",
        payload={"investigation_id": investigation.id}, cause_event=opened_event,
    )
    try:
        db.commit()
        db.refresh(investigation)
        return investigation
    except Exception:
        db.rollback()
        raise


def authorized_investigation(
    db: Session, investigation_id: str, principal: SessionPrincipal,
    *, doctor_requires_active_link: bool = True,
) -> tuple[Investigation, str, str]:
    investigation = db.get(Investigation, investigation_id)
    if investigation is None:
        raise InvestigationNotFound
    role, domain_id = _participant(
        db, investigation, principal, doctor_requires_active_link=doctor_requires_active_link,
    )
    return investigation, role, domain_id


def investigation_list(
    db: Session, principal: SessionPrincipal, *, status: str | None = None,
    counterpart_id: str | None = None, page: int = 1, page_size: int = 10,
) -> tuple[list[Investigation], int, int]:
    role, domain_id = _actor(principal)
    if role == "PATIENT":
        query = select(Investigation).where(Investigation.patient_id == domain_id)
        if counterpart_id:
            query = query.where(Investigation.doctor_id == counterpart_id)
    else:
        query = select(Investigation).join(
            PatientDoctorLink, PatientDoctorLink.id == Investigation.association_id,
        ).where(Investigation.doctor_id == domain_id, PatientDoctorLink.status == "ACTIVE")
        if counterpart_id:
            query = query.where(Investigation.patient_id == counterpart_id)
    if status:
        if status.upper() not in {"OPEN", "CLOSED"}:
            raise ValueError("status must be OPEN or CLOSED")
        query = query.where(Investigation.status == status.upper())
    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
    pages = max(1, (total + page_size - 1) // page_size)
    current_page = min(max(page, 1), pages)
    items = list(db.scalars(
        query.order_by(Investigation.opened_at.desc(), Investigation.id)
        .offset((current_page - 1) * page_size).limit(page_size)
    ))
    return items, total, current_page


def unread_message_count(db: Session, principal: SessionPrincipal) -> int:
    role, domain_id = _actor(principal)
    if role == "PATIENT":
        items = db.scalars(select(Investigation).where(Investigation.patient_id == domain_id)).all()
    else:
        items = db.scalars(select(Investigation).join(
            PatientDoctorLink, PatientDoctorLink.id == Investigation.association_id,
        ).where(Investigation.doctor_id == domain_id, PatientDoctorLink.status == "ACTIVE")).all()
    total = 0
    for item in items:
        position = db.get(InvestigationReadPosition, (item.id, role, domain_id))
        total += db.scalar(select(func.count(InvestigationMessage.id)).where(
            InvestigationMessage.investigation_id == item.id,
            InvestigationMessage.author_role != role,
            InvestigationMessage.sequence > (position.last_read_sequence if position else 0),
        )) or 0
    return total


def investigation_detail(
    db: Session, investigation_id: str, principal: SessionPrincipal,
    *, page: int = 1, page_size: int = 50,
) -> tuple[Investigation, list[InvestigationMessage], int, str, int]:
    investigation, role, domain_id = authorized_investigation(db, investigation_id, principal)
    count = db.scalar(select(func.count(InvestigationMessage.id)).where(
        InvestigationMessage.investigation_id == investigation.id,
    )) or 0
    messages = list(db.scalars(select(InvestigationMessage).where(
        InvestigationMessage.investigation_id == investigation.id,
    ).order_by(InvestigationMessage.sequence).offset((page - 1) * page_size).limit(page_size)))
    position = db.get(InvestigationReadPosition, (investigation.id, role, domain_id))
    unread = db.scalar(select(func.count(InvestigationMessage.id)).where(
        InvestigationMessage.investigation_id == investigation.id,
        InvestigationMessage.author_role != role,
        InvestigationMessage.sequence > (position.last_read_sequence if position else 0),
    )) or 0
    return investigation, messages, count, role, unread


def append_message(
    db: Session, investigation_id: str, principal: SessionPrincipal,
    content: str, idempotency_key: str | None,
) -> InvestigationMessage:
    if not content.strip() or len(content) > 10000:
        raise ValueError("Message must contain 1 to 10000 characters")
    if idempotency_key is not None and (not idempotency_key.strip() or len(idempotency_key) > 128):
        raise ValueError("Invalid idempotency key")
    investigation, role, domain_id = authorized_investigation(db, investigation_id, principal)
    if idempotency_key:
        existing = db.scalar(select(InvestigationMessage).where(
            InvestigationMessage.investigation_id == investigation.id,
            InvestigationMessage.idempotency_key == idempotency_key,
        ))
        if existing is not None:
            if existing.author_role == role and existing.author_domain_id == domain_id:
                return existing
            raise InvestigationConflict("Idempotency key is already in use")
    if investigation.status != "OPEN":
        raise InvestigationConflict("Investigation is closed")
    _lock_active_association(db, investigation)
    current_version = investigation.version
    result = db.execute(update(Investigation).where(
        Investigation.id == investigation.id,
        Investigation.status == "OPEN",
        Investigation.version == current_version,
    ).values(version=current_version + 1, awaiting_role="DOCTOR" if role == "PATIENT" else "PATIENT")
      .execution_options(synchronize_session=False))
    if result.rowcount != 1:
        db.rollback()
        raise InvestigationConflict("Investigation changed or was closed; reload and retry")
    sequence = (db.scalar(select(func.max(InvestigationMessage.sequence)).where(
        InvestigationMessage.investigation_id == investigation.id,
    )) or 0) + 1
    message_id = str(uuid4())
    message = InvestigationMessage(
        id=message_id, investigation_id=investigation.id, author_role=role,
        author_domain_id=domain_id,
        content_encrypted=encrypt_field(content.strip(), table="investigation_messages", column="content", record_id=message_id),
        sequence=sequence, created_at=_now(), idempotency_key=idempotency_key,
    )
    db.add(message)
    event = _activity_event("InvestigationMessageAdded", investigation, principal, {
        "message_id": message_id, "sequence": sequence, "author_role": role,
        "version": current_version + 1,
    })
    db.add(event)
    _add_notification(
        db, recipient_id=_counterpart_account(db, investigation, "DOCTOR" if role == "PATIENT" else "PATIENT"),
        notification_type="investigation_message_added",
        payload={"investigation_id": investigation.id, "sequence": sequence}, cause_event=event,
    )
    try:
        db.commit()
        db.refresh(message)
        return message
    except IntegrityError:
        db.rollback()
        if idempotency_key:
            replay = db.scalar(select(InvestigationMessage).where(
                InvestigationMessage.investigation_id == investigation_id,
                InvestigationMessage.idempotency_key == idempotency_key,
                InvestigationMessage.author_role == role,
                InvestigationMessage.author_domain_id == domain_id,
            ))
            if replay is not None:
                return replay
        raise InvestigationConflict("Message conflicted with a concurrent update")
    except Exception:
        db.rollback()
        raise


def advance_read_position(
    db: Session, investigation_id: str, principal: SessionPrincipal, up_to_sequence: int,
) -> int:
    investigation, role, domain_id = authorized_investigation(db, investigation_id, principal)
    max_sequence = db.scalar(select(func.max(InvestigationMessage.sequence)).where(
        InvestigationMessage.investigation_id == investigation.id,
    )) or 0
    if up_to_sequence < 0 or up_to_sequence > max_sequence:
        raise ValueError("up_to_sequence must refer to a persisted message")
    position = db.get(InvestigationReadPosition, (investigation.id, role, domain_id))
    previous = position.last_read_sequence if position else 0
    if up_to_sequence <= previous:
        return previous
    if position is None:
        position = InvestigationReadPosition(
            investigation_id=investigation.id, participant_role=role,
            participant_domain_id=domain_id, last_read_sequence=up_to_sequence,
        )
        db.add(position)
    else:
        result = db.execute(update(InvestigationReadPosition).where(
            InvestigationReadPosition.investigation_id == investigation.id,
            InvestigationReadPosition.participant_role == role,
            InvestigationReadPosition.participant_domain_id == domain_id,
            InvestigationReadPosition.last_read_sequence == previous,
        ).values(last_read_sequence=up_to_sequence, updated_at=_now()).execution_options(synchronize_session=False))
        if result.rowcount != 1:
            db.rollback()
            current = db.get(InvestigationReadPosition, (investigation.id, role, domain_id))
            if current and current.last_read_sequence >= up_to_sequence:
                return current.last_read_sequence
            raise InvestigationConflict("Read position changed concurrently")
    db.add(_activity_event("InvestigationReadAdvanced", investigation, principal, {
        "participant_role": role, "last_read_sequence_before": previous,
        "last_read_sequence_after": up_to_sequence,
    }))
    try:
        db.commit()
        return up_to_sequence
    except IntegrityError:
        db.rollback()
        current = db.get(InvestigationReadPosition, (investigation.id, role, domain_id))
        if current and current.last_read_sequence >= up_to_sequence:
            return current.last_read_sequence
        raise InvestigationConflict("Read position changed concurrently")
    except Exception:
        db.rollback()
        raise


def close_investigation(
    db: Session, investigation_id: str, principal: SessionPrincipal,
    *, expected_version: int, observation: str | None,
) -> Investigation:
    investigation, role, domain_id = authorized_investigation(db, investigation_id, principal)
    if investigation.status != "OPEN":
        if investigation.status == "CLOSED":
            return investigation
        raise InvestigationConflict("Investigation is closed")
    if investigation.version != expected_version:
        raise InvestigationConflict("Investigation version is stale")
    if observation and len(observation) > 2000:
        raise ValueError("Observation exceeds 2000 characters")
    _lock_active_association(db, investigation)
    now = _now()
    result = db.execute(update(Investigation).where(
        Investigation.id == investigation.id, Investigation.status == "OPEN",
        Investigation.version == expected_version,
    ).values(status="CLOSED", awaiting_role=None, closed_at=now,
             closed_by=domain_id, closed_reason="PARTICIPANT_CLOSED",
             version=expected_version + 1).execution_options(synchronize_session=False))
    if result.rowcount != 1:
        db.rollback()
        raise InvestigationConflict("Investigation changed concurrently; reload and retry")
    event = _activity_event("InvestigationClosed", investigation, principal, {
        "closed_by_role": role, "closed_by_domain_id": domain_id,
        "closed_reason": "PARTICIPANT_CLOSED", "before_version": expected_version,
        "after_version": expected_version + 1,
    })
    db.add(event)
    if observation and observation.strip():
        message_id = str(uuid4())
        sequence = (db.scalar(select(func.max(InvestigationMessage.sequence)).where(
            InvestigationMessage.investigation_id == investigation.id,
        )) or 0) + 1
        db.add(InvestigationMessage(
            id=message_id, investigation_id=investigation.id, author_role=role,
            author_domain_id=domain_id,
            content_encrypted=encrypt_field(observation.strip(), table="investigation_messages", column="content", record_id=message_id),
            sequence=sequence, created_at=now,
        ))
        db.add(_activity_event("InvestigationMessageAdded", investigation, principal, {
            "message_id": message_id, "sequence": sequence, "author_role": role,
            "closing_observation": True,
        }, causation_id=event.id))
    _add_notification(
        db, recipient_id=_counterpart_account(db, investigation, "DOCTOR" if role == "PATIENT" else "PATIENT"),
        notification_type="investigation_closed",
        payload={"investigation_id": investigation.id}, cause_event=event,
    )
    try:
        db.commit()
        db.refresh(investigation)
        return investigation
    except Exception:
        db.rollback()
        raise


def close_for_revoked_association(
    db: Session, association: PatientDoctorLink, revoke_event: ProvenanceEvent,
) -> int:
    open_rows = list(db.scalars(select(Investigation).where(
        Investigation.association_id == association.id,
        Investigation.status == "OPEN",
    )))
    closed = 0
    now = _now()
    for investigation in open_rows:
        result = db.execute(update(Investigation).where(
            Investigation.id == investigation.id, Investigation.status == "OPEN",
        ).values(status="CLOSED", awaiting_role=None, closed_at=now,
                 closed_by="software-agent",
                 closed_reason="ASSOCIATION_REVOKED", version=Investigation.version + 1)
          .execution_options(synchronize_session=False))
        if result.rowcount == 1:
            db.add(_activity_event("InvestigationClosedByAssociationRevocation", investigation, None, {
                "association_id": association.id, "closed_reason": "ASSOCIATION_REVOKED",
                "before_version": investigation.version,
                "after_version": investigation.version + 1,
            }, causation_id=revoke_event.id))
            closed += 1
    return closed


def create_prompts_for_indicators(db: Session, indicators: list[DailyIndicator]) -> int:
    created = 0
    created_by_patient: dict[str, list[tuple[AtypicalDayPrompt, ProvenanceEvent]]] = {}
    for indicator in indicators:
        if not indicator.anomaly_flag:
            continue
        existing = db.scalar(select(AtypicalDayPrompt.id).where(
            AtypicalDayPrompt.patient_id == indicator.patient_id,
            AtypicalDayPrompt.indicator_date == indicator.indicator_date,
        ))
        if existing:
            continue
        prompt = AtypicalDayPrompt(
            id=str(uuid4()), patient_id=indicator.patient_id,
            daily_indicator_id=indicator.id, indicator_date=indicator.indicator_date,
            status="CREATED", created_at=_now(),
        )
        patient = db.get(Patient, indicator.patient_id)
        event = ProvenanceEvent(
            id=str(uuid4()), activity_type="AtypicalDayInvestigationPromptCreated",
            entity_type="atypical_day_prompt", entity_id=prompt.id,
            actor_user_id=None, source_type="software-agent", source_id=indicator.id,
            occurred_at=_now(), prov_json={"activity": "AtypicalDayInvestigationPromptCreated"},
            metadata_json={"patient_id": indicator.patient_id,
                           "daily_indicator_id": indicator.id,
                           "indicator_date": indicator.indicator_date.isoformat()},
        )
        try:
            with db.begin_nested():
                db.add(prompt)
                db.add(event)
                db.flush()
            created += 1
            created_by_patient.setdefault(indicator.patient_id, []).append((prompt, event))
        except IntegrityError:
            # A concurrent analytics run already created the patient/day prompt.
            duplicate = db.scalar(select(AtypicalDayPrompt.id).where(
                AtypicalDayPrompt.patient_id == indicator.patient_id,
                AtypicalDayPrompt.indicator_date == indicator.indicator_date,
            ))
            if duplicate:
                continue
            raise
    for patient_id, prompts_and_events in created_by_patient.items():
        patient = db.get(Patient, patient_id)
        prompts = [prompt for prompt, _event in prompts_and_events]
        causation = prompts_and_events[0][1]
        _add_notification(
            db, recipient_id=patient.user_account_id if patient else None,
            notification_type="atypical_day_prompt",
            payload={
                "prompt_ids": [prompt.id for prompt in prompts],
                "indicator_ids": [prompt.daily_indicator_id for prompt in prompts],
                "dates": [prompt.indicator_date.isoformat() for prompt in prompts],
                "count": len(prompts),
            },
            cause_event=causation,
        )
    return created


def defer_prompt_batch(
    db: Session, patient_id: str, indicator_ids: list[str], principal: SessionPrincipal,
) -> list[AtypicalDayPrompt]:
    if principal.patient is None or principal.patient.id != patient_id:
        raise InvestigationNotFound
    requested_ids = list(dict.fromkeys(indicator_ids))
    prompts = list(db.scalars(select(AtypicalDayPrompt).where(
        AtypicalDayPrompt.patient_id == patient_id,
        AtypicalDayPrompt.daily_indicator_id.in_(requested_ids),
    ).order_by(AtypicalDayPrompt.indicator_date))) if requested_ids else []
    if len(prompts) != len(requested_ids):
        raise InvestigationNotFound
    for prompt in prompts:
        if prompt.status == "DEFERRED":
            continue
        prompt.status = "DEFERRED"
        db.add(ProvenanceEvent(
            id=str(uuid4()), activity_type="AtypicalDayInvestigationPromptDeferred",
            entity_type="atypical_day_prompt", entity_id=prompt.id,
            actor_user_id=principal.account.id, source_type="user", source_id=principal.patient.id,
            occurred_at=_now(), prov_json={"activity": "AtypicalDayInvestigationPromptDeferred"},
            metadata_json={"daily_indicator_id": prompt.daily_indicator_id,
                           "patient_id": patient_id, "batch_count": len(prompts)},
        ))
    try:
        db.commit()
        for prompt in prompts:
            db.refresh(prompt)
        return prompts
    except Exception:
        db.rollback()
        raise


def defer_prompt(db: Session, patient_id: str, indicator_id: str, principal: SessionPrincipal) -> AtypicalDayPrompt:
    return defer_prompt_batch(db, patient_id, [indicator_id], principal)[0]
