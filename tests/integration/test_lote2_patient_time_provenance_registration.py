from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from conftest import World


def test_analytics_and_exact_day_filter_use_patient_local_calendar(world: World):
    from app.db.session import SessionLocal
    from app.models.entities import DailyIndicator, GlucoseRecord, Patient

    patient = world.patient()
    with SessionLocal() as db:
        profile = db.get(Patient, patient.id)
        profile.timezone = "America/Los_Angeles"
        db.add_all([
            GlucoseRecord(patient_id=patient.id, measured_at=datetime(2026, 4, 1, 6, 30),
                          glucose_mg_dl=100, context_label="unspecified"),
            GlucoseRecord(patient_id=patient.id, measured_at=datetime(2026, 4, 1, 7, 30),
                          glucose_mg_dl=110, context_label="unspecified"),
        ])
        db.commit()

    world.compute(patient.id)
    with SessionLocal() as db:
        days = db.scalars(select(DailyIndicator).where(
            DailyIndicator.patient_id == patient.id,
        ).order_by(DailyIndicator.indicator_date)).all()
        assert [(day.indicator_date.isoformat(), day.glucose_event_count) for day in days] == [
            ("2026-03-31", 1), ("2026-04-01", 1),
        ]

    detail = patient.client.get(f"/api/patients/{patient.id}", params={"dates": "2026-03-31"})
    assert detail.status_code == 200, detail.text
    assert [(event["event_date"], event["event_time"]) for event in detail.json()["glucose_events"]] == [
        ("2026-03-31", "23:30"),
    ]


def test_doctor_registration_requires_crm_uf_and_privacy_acceptance(world: World):
    from app.core.crypto import email_lookup
    from app.db.session import SessionLocal
    from app.models.entities import UserAccount

    baseline = world.register_payload("doctor")
    for changes in (
        {"crm": None},
        {"uf": None},
        {"privacy_notice_accepted": False},
        {"privacy_notice_accepted": None},
    ):
        payload = {**baseline, "email": world.unique_email("doctor-required"), **changes}
        response = world.new_client().post("/api/auth/register", json=payload)
        assert response.status_code == 422, (changes, response.text)

    accepted = world.register_payload("doctor")
    accepted["privacy_notice_accepted"] = True
    response = world.new_client().post("/api/auth/register", json=accepted)
    assert response.status_code == 201, response.text
    with SessionLocal() as db:
        account_id = db.scalar(select(UserAccount.id).where(
            UserAccount.email_lookup == email_lookup(accepted["email"]),
        ))
        account = db.get(UserAccount, account_id)
        assert account.privacy_notice_accepted_at is not None


def test_patient_provenance_includes_association_and_investigation_events_and_deduplicates_view(world: World):
    patient, doctor = world.patient(), world.doctor()
    link = world.active_link(patient, doctor)
    investigation = world.open_investigation(patient, doctor)

    history = patient.client.get(f"/api/patients/{patient.id}/provenance")
    assert history.status_code == 200, history.text
    activity_types = {event["activity_type"] for event in history.json()["events"]}
    assert {"AssociationRequested", "AssociationConfirmed", "InvestigationOpened"} <= activity_types

    path = f"/api/patients/{patient.id}/atypical-days"
    assert patient.client.get(path).status_code == 200
    assert patient.client.get(path).status_code == 200
    from app.models.entities import ProvenanceEvent

    assert world.count(
        ProvenanceEvent,
        ProvenanceEvent.activity_type == "AtypicalDayDetailViewed",
        ProvenanceEvent.entity_id == patient.id,
        ProvenanceEvent.actor_user_id == world.account_id(patient),
    ) == 1
