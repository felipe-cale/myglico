"""Exercise B3 association, authorization, provenance, and notification flows in isolated SQLite."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix="myglico-links-") as temp_dir:
    database = Path(temp_dir) / "links.sqlite3"
    database_url = f"sqlite:///{database.as_posix()}"
    sys.path.insert(0, str(ROOT))
    env = os.environ.copy()
    env.update({
        "MYGLICO_DATABASE_URL": database_url,
        "MYGLICO_ARTIFACTS_DIR": temp_dir,
        "MYGLICO_PROVENANCE_DIR": temp_dir,
        "MYGLICO_RAW_DATA_DIR": temp_dir,
        "MYGLICO_ENCRYPTION_KEY_V1": "11" * 32,
        "MYGLICO_LOOKUP_HMAC_KEY": "22" * 32,
        "MYGLICO_ACTIVE_ENCRYPTION_KEY_VERSION": "1",
    })
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT, env=env, check=True)
    os.environ.update(env)

    from fastapi.testclient import TestClient
    from sqlalchemy import func, select, text

    from app.main import app
    from app.db.session import SessionLocal, engine
    from app.models.entities import Notification, PatientDoctorLink, ProvenanceEvent

    def register(client, role, email, name, crm=None, uf=None):
        data = {
            "role": role, "email": email, "password": "SafePass123!",
            "password_confirmation": "SafePass123!", "display_name": name,
        }
        if crm:
            data.update(crm=crm, uf=uf)
        data["privacy_notice_accepted"] = True
        response = client.post("/api/auth/register", json=data)
        assert response.status_code == 201, response.text
        return response.json()

    with TestClient(app, base_url="https://testserver") as anonymous:
        for path in ("/api/patients", "/api/patients/foreign", "/api/patients/foreign/report.pdf", "/api/patients/foreign/glucose-records"):
            if path == "/api/patients" or path.endswith("report.pdf") or path.endswith("/foreign"):
                params = {"start_date": "2026-01-01", "end_date": "2026-01-02"} if path.endswith("report.pdf") else None
                response = anonymous.get(path, params=params)
            else:
                response = anonymous.post(path, json={"measured_at": "2026-01-01T12:00:00", "glucose_mg_dl": 100})
            assert response.status_code == 401, (path, response.status_code)

    with TestClient(app, base_url="https://testserver") as patient, \
         TestClient(app, base_url="https://testserver") as patient_b, \
         TestClient(app, base_url="https://testserver") as doctor, \
         TestClient(app, base_url="https://testserver") as other_doctor:
        p = register(patient, "patient", "patient-a@example.test", "Patient A")
        pb = register(patient_b, "patient", "patient-b@example.test", "Patient B")
        d = register(doctor, "doctor", "doctor-a@example.test", "Doctor A", "CRM-101", "SP")
        d2 = register(other_doctor, "doctor", "doctor-b@example.test", "Doctor B", "CRM-202", "RJ")
        patient_id = p["patient"]["id"]
        foreign_patient_id = pb["patient"]["id"]
        doctor_short = d["doctor"]["short_id"]
        doctor2_short = d2["doctor"]["short_id"]

        denied = patient.get(f"/api/patients/{foreign_patient_id}")
        assert denied.status_code == 404, denied.text
        assert patient.get("/api/patients").status_code == 200

        search = patient.get("/api/doctors/search", params={"short_id": doctor_short}).json()["doctor"]
        assert set(search) == {"short_id", "name", "crm", "uf", "is_demo", "declared_verified", "link_status"}
        assert search["link_status"] == "none"
        assert patient.get("/api/doctors/search", params={"crm": "crm-101", "uf": "sp"}).json()["doctor"]["short_id"] == doctor_short

        requested = patient.post("/api/doctor-links", json={"doctor_short_id": doctor_short})
        assert requested.status_code == 201, requested.text
        first = requested.json()["link"]
        assert first["status"] == "pending"
        assert patient.get("/api/doctor-links").json()["links"][0]["id"] == first["id"]
        assert doctor.get("/api/doctor-links").json()["links"][0]["id"] == first["id"]
        assert patient.get("/api/doctors/search", params={"short_id": doctor_short}).json()["doctor"]["link_status"] == "pending"
        assert len(doctor.get("/api/notifications").json()["notifications"]) == 1
        with SessionLocal() as db:
            assert db.scalar(select(func.count(ProvenanceEvent.id)).where(ProvenanceEvent.activity_type == "AssociationRequested")) == 1

        assert other_doctor.post(f"/api/doctor-links/{first['id']}/confirm", json={"version": 1}).status_code == 404
        assert doctor.get(f"/api/patients/{patient_id}").status_code == 404
        confirmed = doctor.post(f"/api/doctor-links/{first['id']}/confirm", json={"version": 1})
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["link"]["status"] == "active"
        # Replaying the same confirmation is idempotent and creates no second transition event.
        replay = doctor.post(f"/api/doctor-links/{first['id']}/confirm", json={"version": 1})
        assert replay.status_code == 200, replay.text
        with SessionLocal() as db:
            assert db.scalar(select(func.count(ProvenanceEvent.id)).where(ProvenanceEvent.activity_type == "AssociationConfirmed")) == 1

        assert patient.get("/api/doctors/search", params={"short_id": doctor_short}).json()["doctor"]["link_status"] == "active"
        assert doctor.get(f"/api/patients/{patient_id}").status_code == 200
        revoked = patient.post(f"/api/doctor-links/{first['id']}/revoke", json={"version": 2, "reason": "Encerrado"})
        assert revoked.status_code == 200 and revoked.json()["link"]["status"] == "revoked"
        # The same authenticated session is denied on its very next resource request.
        assert doctor.get(f"/api/patients/{patient_id}").status_code == 404
        assert patient.get("/api/doctors/search", params={"short_id": doctor_short}).json()["doctor"]["link_status"] == "none"

        reopened = patient.post("/api/doctor-links", json={"doctor_short_id": doctor_short}).json()["link"]
        assert reopened["id"] != first["id"] and reopened["status"] == "pending"
        assert patient.get("/api/doctors/search", params={"short_id": doctor_short}).json()["doctor"]["link_status"] == "pending"
        assert doctor.post(f"/api/doctor-links/{reopened['id']}/confirm", json={"version": 1}).status_code == 200
        assert doctor.get(f"/api/patients/{patient_id}").status_code == 200
        assert doctor.post(f"/api/doctor-links/{reopened['id']}/revoke", json={"version": 2}).status_code == 200
        assert doctor.get(f"/api/patients/{patient_id}").status_code == 404

        pending = patient.post("/api/doctor-links", json={"doctor_short_id": doctor2_short}).json()["link"]
        rejected = other_doctor.post(f"/api/doctor-links/{pending['id']}/reject", json={"version": 1})
        assert rejected.status_code == 200 and rejected.json()["link"]["status"] == "rejected"
        pending_again = patient.post("/api/doctor-links", json={"doctor_short_id": doctor2_short}).json()["link"]
        assert patient.post(f"/api/doctor-links/{pending_again['id']}/cancel").status_code == 422
        cancelled = patient.post(f"/api/doctor-links/{pending_again['id']}/cancel", json={"version": 1})
        assert cancelled.status_code == 200 and cancelled.json()["link"]["status"] == "cancelled"

        race = patient.post("/api/doctor-links", json={"doctor_short_id": doctor2_short}).json()["link"]
        assert other_doctor.post(f"/api/doctor-links/{race['id']}/confirm", json={"version": 1}).status_code == 200
        conflict = patient.post(f"/api/doctor-links/{race['id']}/cancel", json={"version": 1})
        assert conflict.status_code == 409, conflict.text

        inbox = patient.get("/api/notifications").json()
        assert inbox["unread_count"] >= 3
        notification_id = inbox["notifications"][0]["id"]
        assert patient.post(f"/api/notifications/{notification_id}/read").status_code == 200
        assert patient.get("/api/notifications", params={"unread_only": "true"}).json()["unread_count"] == inbox["unread_count"] - 1

        with SessionLocal() as db:
            event_types = set(db.scalars(select(ProvenanceEvent.activity_type)))
            expected = {"AssociationRequested", "AssociationConfirmed", "AssociationRejected", "AssociationRequestCancelled", "AssociationRevoked", "NotificationCreated", "NotificationRead"}
            assert expected <= event_types, expected - event_types
            assert db.scalar(select(func.count(Notification.id))) >= 7
            link_statuses = set(db.scalars(select(PatientDoctorLink.status)))
            assert {"ACTIVE", "REJECTED", "CANCELLED", "REVOKED"} <= link_statuses, link_statuses

        # A failed provenance write rolls back the link and its notification.
        with SessionLocal() as db:
            notifications_before = db.scalar(select(func.count(Notification.id)))
            db.execute(text("CREATE TRIGGER force_request_event_failure BEFORE INSERT ON provenance_events WHEN NEW.activity_type = 'AssociationRequested' BEGIN SELECT RAISE(ABORT, 'forced provenance failure'); END"))
            db.commit()
        try:
            failed_request_response = patient_b.post("/api/doctor-links", json={"doctor_short_id": doctor_short})
        except Exception as exc:
            assert "forced provenance failure" in str(exc)
        else:
            assert failed_request_response.status_code >= 500, failed_request_response.text
        with SessionLocal() as db:
            assert db.scalar(select(func.count(PatientDoctorLink.id)).where(PatientDoctorLink.patient_id == foreign_patient_id)) == 0
            assert db.scalar(select(func.count(Notification.id))) == notifications_before
            db.execute(text("DROP TRIGGER force_request_event_failure"))
            db.commit()

    engine.dispose()

    print("PASS: CSCW-CA-01..08 and CA-10 lifecycle, privacy, provenance, notifications, idempotency, and conflicts validated in isolated SQLite.")
