"""Validate the B4 CSCW conversation and atypical-day lifecycle on disposable SQLite."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix="myglico-investigations-") as temp_dir:
    sys.path.insert(0, str(ROOT))
    db_file = Path(temp_dir) / "investigations.sqlite3"
    env = os.environ.copy()
    env.update({
        "MYGLICO_DATABASE_URL": f"sqlite:///{db_file.as_posix()}",
        "MYGLICO_ARTIFACTS_DIR": temp_dir,
        "MYGLICO_PROVENANCE_DIR": temp_dir,
        "MYGLICO_RAW_DATA_DIR": temp_dir,
        "MYGLICO_ENCRYPTION_KEY_V1": "33" * 32,
        "MYGLICO_LOOKUP_HMAC_KEY": "44" * 32,
        "MYGLICO_ACTIVE_ENCRYPTION_KEY_VERSION": "1",
    })
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT, env=env, check=True)
    os.environ.update(env)

    from fastapi.testclient import TestClient
    from sqlalchemy import func, select, text

    from app.core.crypto import decrypt_field
    from app.db.session import SessionLocal, engine
    from app.main import app
    from app.core.security import SessionPrincipal
    from app.models.entities import (
        AnalysisRun, AtypicalDayPrompt, DailyIndicator, Doctor, GlucoseRecord,
        Investigation, InvestigationMessage, InvestigationReadPosition,
        Notification, NotificationOutbox, Patient, PatientDoctorLink, ProvenanceEvent,
        UserAccount, UserSession,
    )
    from app.services.analytics import compute_analytics
    from app.services.investigations import InvestigationConflict, append_message

    def register(client, role, email, name, crm=None, uf=None):
        body = {"role": role, "email": email, "password": "SafePass123!",
                "password_confirmation": "SafePass123!", "display_name": name}
        if crm:
            body.update(crm=crm, uf=uf)
        body["privacy_notice_accepted"] = True
        response = client.post("/api/auth/register", json=body)
        assert response.status_code == 201, response.text
        return response.json()

    def active_link(patient, doctor, doctor_short_id):
        requested = patient.post("/api/doctor-links", json={"doctor_short_id": doctor_short_id})
        assert requested.status_code == 201, requested.text
        link = requested.json()["link"]
        accepted = doctor.post(f"/api/doctor-links/{link['id']}/confirm", json={"version": 1})
        assert accepted.status_code == 200, accepted.text
        return link["id"]

    with TestClient(app, base_url="https://testserver") as patient, \
         TestClient(app, base_url="https://testserver") as patient_b, \
         TestClient(app, base_url="https://testserver") as doctor_a, \
         TestClient(app, base_url="https://testserver") as doctor_b:
        p = register(patient, "patient", "cscw-p1@example.test", "CSC Patient")
        p2 = register(patient_b, "patient", "cscw-p2@example.test", "Other Patient")
        d1 = register(doctor_a, "doctor", "cscw-d1@example.test", "Doctor One", "CRM-301", "SP")
        d2 = register(doctor_b, "doctor", "cscw-d2@example.test", "Doctor Two", "CRM-302", "RJ")
        pid, pid2 = p["patient"]["id"], p2["patient"]["id"]
        did1, did2 = d1["doctor"]["id"], d2["doctor"]["id"]
        short1, short2 = d1["doctor"]["short_id"], d2["doctor"]["short_id"]
        link1 = active_link(patient, doctor_a, short1)
        link2 = active_link(patient, doctor_b, short2)

        def seed_indicator(target_patient_id, target_date, anomaly=True):
            with SessionLocal() as db:
                run = AnalysisRun(patient_id=target_patient_id, start_date=target_date,
                                  end_date=target_date, status="completed", trigger_type="test",
                                  algorithm_name="daily_glycemic_summary", algorithm_version="test",
                                  started_at=datetime.utcnow(), finished_at=datetime.utcnow())
                db.add(run)
                db.flush()
                indicator = DailyIndicator(
                    analysis_run_id=run.id, patient_id=target_patient_id,
                    indicator_date=target_date, glucose_event_count=5,
                    avg_glucose=400.0 if anomaly else 110.0, anomaly_flag=anomaly,
                    anomaly_score=-0.5 if anomaly else 0.1,
                )
                db.add(indicator)
                db.commit()
                return indicator.id

        event_id = seed_indicator(pid, date(2026, 5, 2))
        foreign_event_id = seed_indicator(pid2, date(2026, 5, 3))

        # Patient opens with a real event; source ownership is checked server-side.
        wrong_event = patient.post("/api/investigations", json={
            "doctor_id": did1, "atypical_day_event_id": foreign_event_id,
            "title": "Cross patient", "initial_message": "Must be rejected",
        })
        assert wrong_event.status_code == 404, wrong_event.text
        opened = patient.post("/api/investigations", json={
            "doctor_id": did1, "atypical_day_event_id": event_id,
            "title": "Unexpected reading", "initial_message": "Please review this day.",
        })
        assert opened.status_code == 201, opened.text
        inv1 = opened.json()["investigation"]
        assert inv1["status"] == "open" and inv1["awaiting_role"] == "doctor"
        first_detail = patient.get(f"/api/investigations/{inv1['id']}").json()
        assert first_detail["messages"][0]["sequence"] == 1
        assert first_detail["messages"][0]["author_role"] == "patient"

        # A patient with multiple active doctors must select one; conversations are isolated.
        opened_without_event = patient.post("/api/investigations", json={
            "doctor_id": did2, "title": "Manual question", "initial_message": "No event attached.",
        })
        assert opened_without_event.status_code == 201, opened_without_event.text
        inv2 = opened_without_event.json()["investigation"]
        assert inv2["atypical_day_event_id"] is None
        opened_by_doctor = doctor_b.post("/api/investigations", json={
            "patient_id": pid, "title": "Doctor initiated", "initial_message": "I have a question.",
        })
        assert opened_by_doctor.status_code == 201, opened_by_doctor.text
        inv3 = opened_by_doctor.json()["investigation"]
        assert inv3["opened_by_role"] == "doctor"
        doctor_a_list = doctor_a.get("/api/investigations").json()["investigations"]
        assert {row["id"] for row in doctor_a_list} == {inv1["id"]}
        assert doctor_a.get(f"/api/investigations/{inv2['id']}").status_code == 404
        assert doctor_b.get(f"/api/investigations/{inv1['id']}").status_code == 404

        # Author is server-resolved, sequence is monotonic, and replay is idempotent.
        msg2 = doctor_a.post(f"/api/investigations/{inv1['id']}/messages", json={"content": "Reviewed."})
        assert msg2.status_code == 201 and msg2.json()["message"]["sequence"] == 2
        msg3 = patient.post(f"/api/investigations/{inv1['id']}/messages", json={
            "content": "Thank you.", "idempotency_key": "patient-msg-once",
        })
        assert msg3.status_code == 201 and msg3.json()["message"]["sequence"] == 3
        replay = patient.post(f"/api/investigations/{inv1['id']}/messages", json={
            "content": "Thank you.", "idempotency_key": "patient-msg-once",
        })
        assert replay.status_code == 201 and replay.json()["message"]["id"] == msg3.json()["message"]["id"]
        with SessionLocal() as db:
            assert db.scalar(select(func.count(InvestigationMessage.id)).where(
                InvestigationMessage.investigation_id == inv1["id"]
            )) == 3
            assert db.scalar(select(func.count(ProvenanceEvent.id)).where(
                ProvenanceEvent.activity_type == "InvestigationMessageAdded",
                ProvenanceEvent.entity_id == inv1["id"],
            )) == 3
            initial = db.scalar(select(InvestigationMessage).where(
                InvestigationMessage.investigation_id == inv1["id"], InvestigationMessage.sequence == 1
            ))
            assert b"Please review this day." not in initial.content_encrypted
            assert decrypt_field(initial.content_encrypted, table="investigation_messages", column="content", record_id=initial.id) == "Please review this day."
            assert db.scalar(select(Investigation.title_encrypted).where(Investigation.id == inv1["id"])) != b"Unexpected reading"

        read = patient.post(f"/api/investigations/{inv1['id']}/read", json={"up_to_sequence": 3})
        assert read.status_code == 200 and read.json()["last_read_sequence"] == 3
        assert patient.post(f"/api/investigations/{inv1['id']}/read", json={"up_to_sequence": 3}).status_code == 200
        with SessionLocal() as db:
            assert db.scalar(select(func.count(ProvenanceEvent.id)).where(
                ProvenanceEvent.activity_type == "InvestigationReadAdvanced",
                ProvenanceEvent.entity_id == inv1["id"],
            )) == 1

        closed = doctor_a.post(f"/api/investigations/{inv1['id']}/close", json={
            "version": 3, "observation": "Encerrado em comum acordo.",
        })
        assert closed.status_code == 200 and closed.json()["investigation"]["status"] == "closed"
        after_close = patient.post(f"/api/investigations/{inv1['id']}/messages", json={"content": "Late"})
        assert after_close.status_code == 409
        assert patient.get(f"/api/investigations/{inv1['id']}").json()["pagination"]["total"] == 4
        # Either participant can close without acceptance by the counterpart.
        # A sender that read OPEN before the close still loses the conditional write.
        stale_db = SessionLocal()
        stale_investigation = stale_db.get(Investigation, inv2["id"])
        assert stale_investigation.status == "OPEN"
        stale_db.expunge(stale_investigation)
        stale_db.rollback()
        assert patient.post(f"/api/investigations/{inv2['id']}/close", json={"version": 1}).status_code == 200
        stale_db.add(stale_investigation)
        token = patient.cookies.get("myglico_session")
        stale_session = stale_db.get(UserSession, token)
        stale_principal = SessionPrincipal(
            session=stale_session, account=stale_db.get(UserAccount, stale_session.user_account_id),
            patient=stale_db.get(Patient, pid), doctor=None,
        )
        try:
            append_message(stale_db, inv2["id"], stale_principal, "Concurrent late message", None)
            raise AssertionError("conditional write must reject a sender with stale OPEN state")
        except InvestigationConflict:
            pass
        finally:
            stale_db.close()
        with SessionLocal() as db:
            assert db.scalar(select(func.count(InvestigationMessage.id)).where(
                InvestigationMessage.investigation_id == inv2["id"]
            )) == 1

        # Leave two conversations open on one association; B3 revoke closes them atomically.
        revoke_open_1 = patient.post("/api/investigations", json={
            "doctor_id": did1, "title": "For revocation", "initial_message": "Keep history.",
        }).json()["investigation"]
        revoke_open_2 = patient.post("/api/investigations", json={
            "doctor_id": did1, "title": "For revocation two", "initial_message": "Keep this too.",
        }).json()["investigation"]
        link = next(row for row in patient.get("/api/doctor-links").json()["links"] if row["id"] == link1)
        revoked = patient.post(f"/api/doctor-links/{link1}/revoke", json={"version": link["version"]})
        assert revoked.status_code == 200 and revoked.json()["link"]["status"] == "revoked"
        with SessionLocal() as db:
            for inv in (revoke_open_1, revoke_open_2):
                stored = db.get(Investigation, inv["id"])
                assert stored.status == "CLOSED" and stored.closed_reason == "ASSOCIATION_REVOKED"
                assert stored.closed_by == "software-agent"
                event = db.scalar(select(ProvenanceEvent).where(
                    ProvenanceEvent.activity_type == "InvestigationClosedByAssociationRevocation",
                    ProvenanceEvent.entity_id == inv["id"],
                ))
                cause = db.scalar(select(ProvenanceEvent).where(
                    ProvenanceEvent.activity_type == "AssociationRevoked",
                    ProvenanceEvent.entity_id == link1,
                ))
                assert event is not None and cause is not None
                assert event.metadata_json["causation_event_id"] == cause.id
        assert patient.get(f"/api/investigations/{revoke_open_1['id']}").status_code == 200
        assert doctor_a.get(f"/api/investigations/{revoke_open_1['id']}").status_code == 404
        assert patient.post(f"/api/investigations/{revoke_open_1['id']}/messages", json={"content": "Closed"}).status_code == 409
        # Reauthorization creates a new association cycle; both doctors are selectable again.
        assert active_link(patient, doctor_a, short1) != link1

        # The analytics writer creates one prompt per patient/day, notification and outbox,
        # but leaves opening to the patient. Reprocessing preserves the old event reference.
        with SessionLocal() as db:
            start = date(2026, 6, 1)
            for offset in range(10):
                day = start + timedelta(days=offset)
                value = 480.0 if offset == 9 else 105.0
                for reading in range(5):
                    db.add(GlucoseRecord(
                        patient_id=pid, measured_at=datetime.combine(day, datetime.min.time()) + timedelta(hours=reading * 3),
                        glucose_mg_dl=value, context_label=None,
                    ))
            db.commit()
        with SessionLocal() as db:
            compute_analytics(db, patient_id=pid, trigger_type="test")
        with SessionLocal() as db:
            latest_indicator = db.scalar(select(DailyIndicator).where(
                DailyIndicator.patient_id == pid,
            ).order_by(DailyIndicator.indicator_date.desc()))
            global_run = db.get(AnalysisRun, latest_indicator.analysis_run_id)
            global_run.patient_id = None
            # Add a second anomaly in a non-consecutive date to exercise the exact-list filter.
            extra_day = latest_indicator.indicator_date + timedelta(days=4)
            db.add(DailyIndicator(
                analysis_run_id=global_run.id, patient_id=pid, indicator_date=extra_day,
                glucose_event_count=5, avg_glucose=440.0, anomaly_flag=True,
                anomaly_score=-0.6,
            ))
            db.commit()
            prompts = list(db.scalars(select(AtypicalDayPrompt).where(AtypicalDayPrompt.patient_id == pid)))
            assert prompts, "analytics did not flag the extreme day in the deterministic fixture"
            prompt = prompts[0]
            original_indicator_id = prompt.daily_indicator_id
            prompt_date = prompt.indicator_date
            assert db.scalar(select(func.count(Investigation.id)).where(
                Investigation.atypical_day_event_id == original_indicator_id
            )) == 0
            assert db.scalar(select(func.count(NotificationOutbox.id))) >= 1
        atypical_days = patient.get(f"/api/patients/{pid}/atypical-days").json()["days"]
        assert any(row["indicator_id"] == original_indicator_id and row["date"] == prompt_date.isoformat() for row in atypical_days)
        assert any(row["indicator_id"] == original_indicator_id for row in atypical_days), \
            "patient indicators must be found even when their AnalysisRun is global (patient_id NULL)"
        date_filtered = patient.get(f"/api/patients/{pid}/atypical-days", params={
            "start_date": prompt_date.isoformat(), "end_date": prompt_date.isoformat(),
        }).json()["days"]
        assert date_filtered and all(row["date"] == prompt_date.isoformat() for row in date_filtered)
        exact_days = patient.get(f"/api/patients/{pid}/atypical-days", params={
            "dates": f"{prompt_date.isoformat()},{extra_day.isoformat()}"
        }).json()["days"]
        assert {row["date"] for row in exact_days} == {prompt_date.isoformat(), extra_day.isoformat()}
        assert len(exact_days) == 2, "dates= must select exact values without filling the interval"
        exact_detail = patient.get(f"/api/patients/{pid}", params={
            "dates": extra_day.isoformat(),
            "start_date": prompt_date.isoformat(),
            "end_date": prompt_date.isoformat(),
        })
        assert exact_detail.status_code == 200, exact_detail.text
        assert [item["date"] for item in exact_detail.json()["daily_indicators"]] == [extra_day.isoformat()]
        history = patient.get(f"/api/patients/{pid}/provenance")
        assert history.status_code == 200
        assert {event["activity_type"] for event in history.json()["events"]} >= {
            "AtypicalDayDetailViewed", "PatientDetailFilterApplied"
        }
        prompts_api = patient.get(f"/api/patients/{pid}/atypical-day-prompts").json()["prompts"]
        matching_prompt = next(row for row in prompts_api if original_indicator_id in row["indicator_ids"])
        assert matching_prompt["status"] == "created"
        defer = patient.post("/api/atypical-day-prompts/defer", json={
            "indicator_ids": matching_prompt["indicator_ids"],
        })
        assert defer.status_code == 200
        assert {row["status"] for row in defer.json()["prompts"]} == {"deferred"}
        remaining_batches = patient.get(f"/api/patients/{pid}/atypical-day-prompts").json()["prompts"]
        assert all(row["status"] == "deferred" for row in remaining_batches)
        manual_after_defer = patient.post("/api/investigations", json={
            "doctor_id": did2, "atypical_day_event_id": original_indicator_id,
            "title": "Manual after defer", "initial_message": "I still want to ask.",
        })
        assert manual_after_defer.status_code == 201, manual_after_defer.text
        manual_id = manual_after_defer.json()["investigation"]["id"]
        assert manual_after_defer.json()["investigation"]["doctor_id"] == did2
        assert any(row["indicator_id"] == original_indicator_id and row["has_investigation"]
                   for row in patient.get(f"/api/patients/{pid}/atypical-days").json()["days"])
        with SessionLocal() as db:
            before_prompt_count = db.scalar(select(func.count(AtypicalDayPrompt.id)).where(
                AtypicalDayPrompt.patient_id == pid,
            ))
            atypical_notifications_before = db.scalar(select(func.count(Notification.id)).where(
                Notification.notification_type == "atypical_day_prompt",
                Notification.recipient_user_account_id == db.get(Patient, pid).user_account_id,
            ))
            assert atypical_notifications_before == 1, "one batch should create at most one atypical-day notification per patient"
            historical = db.get(Investigation, manual_after_defer.json()["investigation"]["id"])
            historical_id = historical.id
            assert historical.atypical_day_event_id == original_indicator_id
            opened_event = db.scalar(select(ProvenanceEvent).where(
                ProvenanceEvent.activity_type == "InvestigationOpened",
                ProvenanceEvent.entity_id == manual_id,
            ))
            chosen_doctor_account = db.get(Doctor, did2).user_account_id
            other_doctor_account = db.get(Doctor, did1).user_account_id
            targeted_notifications = list(db.scalars(select(Notification).where(
                Notification.causation_event_id == opened_event.id,
            )))
            assert len(targeted_notifications) == 1
            assert targeted_notifications[0].recipient_user_account_id == chosen_doctor_account
            assert targeted_notifications[0].recipient_user_account_id != other_doctor_account
            assert db.get(DailyIndicator, original_indicator_id) is not None
            notifications_before = db.scalar(select(func.count(Notification.id)))
            outbox_before = db.scalar(select(func.count(NotificationOutbox.id)))
            db.execute(text("CREATE TRIGGER fail_investigation_provenance BEFORE INSERT ON provenance_events WHEN NEW.activity_type = 'InvestigationOpened' BEGIN SELECT RAISE(ABORT, 'forced investigation provenance failure'); END"))
            db.commit()
        try:
            patient.post("/api/investigations", json={
                "doctor_id": did2, "title": "Must rollback", "initial_message": "No partial records.",
            })
            raise AssertionError("provenance trigger should reject investigation opening")
        except Exception as exc:
            assert "forced investigation provenance failure" in str(exc)
        with SessionLocal() as db:
            assert db.scalar(select(func.count(Investigation.id)).where(
                Investigation.patient_id == pid, Investigation.title_encrypted.is_not(None),
            )) == 6  # inv1, inv2, inv3, two revoked, and the manual post-defer conversation.
            assert db.scalar(select(func.count(Notification.id))) == notifications_before
            assert db.scalar(select(func.count(NotificationOutbox.id))) == outbox_before
            db.execute(text("DROP TRIGGER fail_investigation_provenance"))
            db.commit()

        with SessionLocal() as db:
            compute_analytics(db, patient_id=pid, trigger_type="test_reprocess")
        with SessionLocal() as db:
            after_prompt_count = db.scalar(select(func.count(AtypicalDayPrompt.id)).where(
                AtypicalDayPrompt.patient_id == pid,
            ))
            assert after_prompt_count == before_prompt_count
            assert db.scalar(select(func.count(Notification.id)).where(
                Notification.notification_type == "atypical_day_prompt",
                Notification.recipient_user_account_id == db.get(Patient, pid).user_account_id,
            )) == atypical_notifications_before
            assert db.get(Investigation, historical_id).atypical_day_event_id == original_indicator_id
            assert db.get(DailyIndicator, original_indicator_id) is not None
            assert db.scalar(select(func.count(AtypicalDayPrompt.id)).where(
                AtypicalDayPrompt.patient_id == pid, AtypicalDayPrompt.indicator_date == prompt_date,
            )) == 1

    engine.dispose()
    print("PASS: backend integration coverage for CSCW-CA-13..23, CA-26, CA-28..30, CA-36..38, global-run atypical lookup, exact dates filtering, and revoked-doctor 404 on isolated SQLite. UI-only CA-24/25/27 remains with the frontend owner.")
