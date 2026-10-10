from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from conftest import World


def test_manual_datetime_local_is_stored_as_utc_and_displayed_on_same_patient_day(world: World):
    from app.db.session import SessionLocal
    from app.models.entities import GlucoseRecord, Patient

    patient = world.patient()
    local_time = "2026-10-08T00:30:00"
    response = patient.client.post(
        f"/api/patients/{patient.id}/glucose-records",
        json={"measured_at": local_time, "glucose_mg_dl": 123.0, "context_label": "unspecified"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["glucose_record"]["measured_at"] == "2026-10-08T00:30:00"

    with SessionLocal() as db:
        record = db.scalar(select(GlucoseRecord).where(GlucoseRecord.patient_id == patient.id))
        profile = db.get(Patient, patient.id)
        assert profile.timezone == "America/Sao_Paulo"
        assert record.measured_at == datetime(2026, 10, 8, 3, 30)

    detail = patient.client.get(
        f"/api/patients/{patient.id}", params={"dates": "2026-10-08"},
    )
    assert detail.status_code == 200, detail.text
    assert [(event["event_date"], event["event_time"]) for event in detail.json()["glucose_events"]] == [
        ("2026-10-08", "00:30"),
    ]


def test_doctor_provenance_only_contains_that_doctors_link_and_investigation(world: World):
    patient = world.patient()
    doctor_a, doctor_b = world.doctor(), world.doctor()
    link_a = world.active_link(patient, doctor_a)
    link_b = world.active_link(patient, doctor_b)
    investigation_b = world.open_investigation(
        patient, doctor_b, title="Private to doctor B", message="B-only context",
    )

    assert doctor_a.client.get(f"/api/investigations/{investigation_b['id']}").status_code == 404
    history_a = doctor_a.client.get(f"/api/patients/{patient.id}/provenance")
    history_b = doctor_b.client.get(f"/api/patients/{patient.id}/provenance")
    history_patient = patient.client.get(f"/api/patients/{patient.id}/provenance")
    assert history_a.status_code == history_b.status_code == history_patient.status_code == 200

    events_a = history_a.json()["events"]
    events_b = history_b.json()["events"]
    events_patient = history_patient.json()["events"]
    assert not any(event["activity_type"] == "InvestigationOpened" for event in events_a)
    assert any(event["activity_type"] == "InvestigationOpened" for event in events_b)
    assert {event["metadata"].get("doctor_id") for event in events_a if event["activity_type"].startswith("Association")} == {doctor_a.id}
    assert {event["metadata"].get("doctor_id") for event in events_b if event["activity_type"].startswith("Association")} == {doctor_b.id}
    assert doctor_b.id not in {event["metadata"].get("doctor_id") for event in events_a}
    assert {doctor_a.id, doctor_b.id} <= {
        event["metadata"].get("doctor_id") for event in events_patient
    }
    assert any(event["activity_type"] == "InvestigationOpened" for event in events_patient)


def test_doctor_provenance_excludes_previous_cycle_after_reassociation(world: World):
    patient, doctor = world.patient(), world.doctor()
    old_link = world.active_link(patient, doctor)
    old_investigation = world.open_investigation(patient, doctor, title="Old cycle", message="Before revoke")
    revoked = patient.client.post(f"/api/doctor-links/{old_link['id']}/revoke", json={"version": old_link["version"]})
    assert revoked.status_code == 200, revoked.text
    new_link = world.active_link(patient, doctor)
    assert new_link["id"] != old_link["id"]

    history = doctor.client.get(f"/api/patients/{patient.id}/provenance")
    assert history.status_code == 200, history.text
    leaked = [event for event in history.json()["events"]
              if old_link["id"] in str(event["metadata"]) or old_investigation["id"] in str(event["metadata"])
              or event["activity_type"] == "InvestigationOpened"]
    assert leaked == []
    association_events = sorted(event["activity_type"] for event in history.json()["events"]
                                if event["activity_type"].startswith("Association"))
    assert association_events == ["AssociationConfirmed", "AssociationRequested"]

    patient_history = patient.client.get(f"/api/patients/{patient.id}/provenance").json()["events"]
    assert any(event["activity_type"] == "InvestigationOpened" for event in patient_history)


def test_atypical_days_has_investigation_ignores_previous_cycle_after_reassociation(world: World):
    from datetime import date

    patient, doctor = world.patient(), world.doctor()
    old_link = world.active_link(patient, doctor)
    indicator_id = world.seed_indicator(patient.id, date(2026, 6, 10))
    world.open_investigation(patient, doctor, event_id=indicator_id, title="Old cycle day")

    def flag(actor):
        response = actor.client.get(f"/api/patients/{patient.id}/atypical-days")
        assert response.status_code == 200, response.text
        return {day["indicator_id"]: day["has_investigation"] for day in response.json()["days"]}[indicator_id]

    assert flag(doctor) is True
    revoked = patient.client.post(f"/api/doctor-links/{old_link['id']}/revoke", json={"version": old_link["version"]})
    assert revoked.status_code == 200, revoked.text
    world.active_link(patient, doctor)
    assert flag(doctor) is False
    assert flag(patient) is True


def test_patient_registration_records_privacy_notice_acknowledgement(world: World):
    from app.core.crypto import email_lookup
    from app.db.session import SessionLocal
    from app.models.entities import UserAccount

    for missing in ({"privacy_notice_accepted": False}, {"privacy_notice_accepted": None}, None):
        payload = world.register_payload("patient", email=world.unique_email("patient-privacy"))
        if missing is None:
            payload.pop("privacy_notice_accepted")
        else:
            payload.update(missing)
        response = world.new_client().post("/api/auth/register", json=payload)
        assert response.status_code == 422, (missing, response.text)

    accepted = world.register_payload("patient")
    response = world.new_client().post("/api/auth/register", json=accepted)
    assert response.status_code == 201, response.text
    with SessionLocal() as db:
        account = db.scalar(select(UserAccount).where(UserAccount.email_lookup == email_lookup(accepted["email"])))
        assert account.privacy_notice_accepted_at is not None
