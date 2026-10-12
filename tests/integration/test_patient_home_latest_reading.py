"""Patient home: the dashboard carries the patient's own latest reading."""
from __future__ import annotations

from datetime import datetime, timedelta

from conftest import World


def _post_reading(patient, measured_at: str, value: float) -> None:
    response = patient.client.post(
        f"/api/patients/{patient.id}/glucose-records",
        json={"measured_at": measured_at, "glucose_mg_dl": value, "context_label": "unspecified"},
    )
    assert response.status_code == 201, response.text


def test_patient_dashboard_returns_latest_reading_in_local_time(world: World):
    patient = world.patient()
    assert patient.client.get("/api/dashboard").json()["latest_reading"] is None

    earlier = (datetime.now() - timedelta(days=2)).replace(hour=8, minute=15, second=0, microsecond=0)
    later = (datetime.now() - timedelta(days=1)).replace(hour=21, minute=40, second=0, microsecond=0)
    _post_reading(patient, later.isoformat(timespec="minutes"), 142)
    _post_reading(patient, earlier.isoformat(timespec="minutes"), 98)

    latest = patient.client.get("/api/dashboard").json()["latest_reading"]
    assert latest["glucose_mg_dl"] == 142
    assert latest["measured_at"].startswith(later.isoformat(timespec="minutes"))


def test_doctor_dashboard_has_no_latest_reading(world: World):
    doctor, patient = world.doctor(), world.patient()
    world.active_link(patient, doctor)
    _post_reading(patient, (datetime.now() - timedelta(hours=3)).isoformat(timespec="minutes"), 120)
    assert doctor.client.get("/api/dashboard").json()["latest_reading"] is None
