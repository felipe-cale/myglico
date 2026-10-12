from __future__ import annotations

from datetime import datetime
from hashlib import sha256

from sqlalchemy.orm import Session

from app.core.patient_time import local_datetime_to_utc_naive, patient_local_date
from app.models.entities import GlucoseRecord, GlucoseRecordSource, Patient, ProvenanceEvent
from app.services.analysis_queue import mark_analysis_pending
from app.services.daily_metrics import refresh_basic_daily_metrics


def _content_hash(payload: object) -> str:
    return sha256(repr(payload).encode("utf-8")).hexdigest()


def create_patient(db: Session, name: str, email: str | None = None) -> Patient:
    patient = Patient(name=name, email=email)
    db.add(patient)
    db.commit()
    db.refresh(patient)
    return patient


def create_manual_glucose_record(
    db: Session,
    patient: Patient,
    measured_at: datetime,
    glucose_mg_dl: float,
    context_label: str | None = None,
    notes: str | None = None,
    actor_user_id: str | None = None,
) -> GlucoseRecord:
    measured_at_utc = local_datetime_to_utc_naive(measured_at, patient.timezone)
    try:
        glucose_record = GlucoseRecord(
            patient_id=patient.id,
            measured_at=measured_at_utc,
            glucose_mg_dl=glucose_mg_dl,
            context_label=context_label,
            notes=notes,
        )
        db.add(glucose_record)
        db.flush()

        source = GlucoseRecordSource(
            glucose_record_id=glucose_record.id,
            source_type="manual",
            actor_user_id=actor_user_id,
            entered_at=datetime.utcnow(),
            metadata_json={"channel": "api"},
        )
        db.add(source)

        prov_payload = {
            "entity": {"glucose_record": glucose_record.id},
            "activity": "manual_glucose_entry",
            "agent": actor_user_id,
            "wasGeneratedBy": glucose_record.id,
            "wasAttributedTo": actor_user_id,
        }
        db.add(
            ProvenanceEvent(
                activity_type="manual_glucose_entry",
                entity_type="glucose_record",
                entity_id=glucose_record.id,
                actor_user_id=actor_user_id,
                source_type="manual",
                source_id=source.id,
                occurred_at=datetime.utcnow(),
                prov_json=prov_payload,
                metadata_json={"patient_id": patient.id, "context_label": context_label},
                content_hash=_content_hash(prov_payload),
            )
        )
        local_day = patient_local_date(measured_at_utc, patient.timezone)
        mark_analysis_pending(db, patient.id, local_day, "manual_entry")
        # The API cannot run the pandas/sklearn pipeline; keep the day's basic
        # indicators correct now and leave anomaly/cluster to the offline run.
        refresh_basic_daily_metrics(db, patient.id, patient.timezone, local_day)
        db.commit()
        db.refresh(glucose_record)
        return glucose_record
    except Exception:
        db.rollback()
        raise
