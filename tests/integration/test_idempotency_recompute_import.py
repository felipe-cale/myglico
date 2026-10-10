"""Idempotency, UCI demo import and reprocessing preservation.

Covers CSCW-CA-34, AUT-CA-16, AUT-CA-17, CSCW-CA-11, CSCW-CA-12, CSCW-CA-45,
AUT-CA-21 and CSCW-CA-22.

The UCI criteria run the real ``scripts/import_uci_diabetes.py`` entry point
with ``--provision-demo-accounts`` but no network: the download step is
replaced by a small offline fixture in the UCI file format (same approach as
``scripts/validate_uci_demo_provisioning.py``).
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from conftest import REPO_ROOT, World

UCI_PATIENT_COUNT = 3
UCI_DAYS = 60
UCI_START = date(1991, 4, 21)


def _write_uci_fixture(root: Path):
    from app.services.uci_importer import ExtractedDataset

    root.mkdir(parents=True, exist_ok=True)
    files = []
    for index in range(1, UCI_PATIENT_COUNT + 1):
        lines = []
        for offset in range(UCI_DAYS):
            day = UCI_START + timedelta(days=offset)
            stamp = day.strftime("%m-%d-%Y")
            base = 110 + ((offset * 37 + index * 11) % 40)
            # A handful of clearly abnormal days per patient so the per-patient
            # IsolationForest flags several historical atypical days.
            if offset in (7, 23, 41, 55):
                values = (base + 240, base + 260, 45, base + 230)
            else:
                values = (base, base + 15, base - 10, base + 5)
            for (slot, code), value in zip((("08:00", 58), ("12:00", 60), ("18:00", 62), ("22:00", 48)), values):
                lines.append(f"{stamp}\t{slot}\t{code}\t{value}")
        path = root / f"data-{index:02d}"
        path.write_text("\n".join(lines), encoding="utf-8")
        files.append(path)
    return ExtractedDataset(root_dir=root, patient_files=files, data_codes_path=root / "Data-Codes",
                            domain_description_path=root / "Domain-Description", zip_path=root / "fixture.zip")


def _uci_snapshot() -> dict:
    from sqlalchemy import func, select

    from app.db.session import SessionLocal
    from app.models.entities import (
        AtypicalDayPrompt, DataSource, Doctor, GlucoseRecordSource, Notification, Patient,
        PatientDoctorLink, PatientSourceLink, ProvenanceEvent, UserAccount,
    )

    with SessionLocal() as db:
        source = db.scalar(select(DataSource).where(DataSource.name == "UCI Diabetes"))
        # test_provenance_events.py attaches its own "it-*" patients to the same source.
        links = list(db.scalars(select(PatientSourceLink).where(
            PatientSourceLink.data_source_id == source.id,
            PatientSourceLink.external_patient_code.not_like("it-%"),
        ).order_by(PatientSourceLink.external_patient_code)))
        patient_ids = [link.patient_id for link in links]
        patients = [db.get(Patient, pid) for pid in patient_ids]
        account_ids = [p.user_account_id for p in patients]
        accounts = [db.get(UserAccount, aid) if aid else None for aid in account_ids]
        demo_doctor = db.scalar(select(Doctor).where(Doctor.is_demo.is_(True)))
        return {
            "patient_ids": patient_ids,
            "patient_short_ids": [p.short_id for p in patients],
            "accounts": [(a.id, bytes(a.email_encrypted), a.email_lookup, a.password_hash, a.is_demo) if a else None
                         for a in accounts],
            "demo_doctor": (demo_doctor.id, demo_doctor.short_id, demo_doctor.user_account_id) if demo_doctor else None,
            "links": [tuple(db.execute(select(PatientDoctorLink.id, PatientDoctorLink.status, PatientDoctorLink.version)
                                       .where(PatientDoctorLink.patient_id == pid)).all()) for pid in patient_ids],
            "demo_events": sorted(db.scalars(select(ProvenanceEvent.id).where(
                ProvenanceEvent.activity_type == "DemoAssociationProvisioned",
                ProvenanceEvent.entity_id.in_(select(PatientDoctorLink.id).where(
                    PatientDoctorLink.patient_id.in_(patient_ids)))))),
            "record_sources": db.scalar(select(func.count(GlucoseRecordSource.id))
                                        .where(GlucoseRecordSource.source_type == "dataset")),
            "prompts": {pid: sorted((p.indicator_date.isoformat(), p.daily_indicator_id) for p in db.scalars(
                select(AtypicalDayPrompt).where(AtypicalDayPrompt.patient_id == pid))) for pid in patient_ids},
            "prompt_notifications": {aid: db.scalar(select(func.count(Notification.id)).where(
                Notification.recipient_user_account_id == aid,
                Notification.notification_type == "atypical_day_prompt")) for aid in account_ids if aid},
        }


@pytest.fixture(scope="module")
def uci_import(app, tmp_path_factory):
    """Run the demo import once (offline fixture) and expose a re-run helper."""
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    import app.services.uci_importer as importer
    import scripts.import_uci_diabetes as import_script

    dataset = _write_uci_fixture(tmp_path_factory.mktemp("uci") / "dataset")
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(importer, "download_and_extract_dataset", lambda: dataset)

        def run():
            import_script.main(["--provision-demo-accounts"])
            return _uci_snapshot()

        first = run()
        yield {"first": first, "run": run}


def _demo_account_email(account_id: str) -> str:
    from app.db.session import SessionLocal
    from app.models.entities import UserAccount

    with SessionLocal() as db:
        return db.get(UserAccount, account_id).email


def test_cscw_ca_34_replayed_request_produces_one_effect_and_one_success_event(world: World):
    """CSCW-CA-34: replaying a request with the same idempotency key is single-effect.

    Repeat an investigation opening / message send / link request with the same
    key: assert one row, one success event set, and the same response body.
    """
    from app.models.entities import InvestigationMessage, Notification, PatientDoctorLink

    patient, doctor = world.patient(), world.doctor()
    doctor_account = world.account_id(doctor)

    # link request replay -> same PENDING link, one AssociationRequested, one notification
    first = patient.client.post("/api/doctor-links", json={"doctor_short_id": doctor.short_id})
    replay = patient.client.post("/api/doctor-links", json={"doctor_short_id": doctor.short_id})
    assert first.status_code == 201 and replay.status_code == 200
    assert first.json() == replay.json()
    link = first.json()["link"]
    assert world.count(PatientDoctorLink, PatientDoctorLink.patient_id == patient.id) == 1
    assert len(world.events("AssociationRequested", link["id"])) == 1
    assert world.count(Notification, Notification.recipient_user_account_id == doctor_account) == 1

    # confirm replay -> one AssociationConfirmed
    for _ in range(3):
        response = doctor.client.post(f"/api/doctor-links/{link['id']}/confirm", json={"version": 1})
        assert response.status_code == 200 and response.json()["link"]["status"] == "active"
    assert len(world.events("AssociationConfirmed", link["id"])) == 1

    # message replay with the same idempotency_key -> one row, one event, one notification
    investigation = world.open_investigation(patient, doctor)
    body = {"content": "Exactly once", "idempotency_key": "it-replay-key"}
    notifications_before = world.count(Notification, Notification.recipient_user_account_id == doctor_account)
    responses = [patient.client.post(f"/api/investigations/{investigation['id']}/messages", json=body) for _ in range(3)]
    assert {r.status_code for r in responses} == {201}
    assert len({r.json()["message"]["id"] for r in responses}) == 1
    assert responses[0].json() == responses[2].json()
    assert world.count(InvestigationMessage, InvestigationMessage.investigation_id == investigation["id"]) == 2
    assert len(world.events("InvestigationMessageAdded", investigation["id"])) == 2
    assert world.count(Notification, Notification.recipient_user_account_id == doctor_account) == notifications_before + 1
    # the key is bound to its author: the counterpart cannot reuse it to inject content
    hijack = doctor.client.post(f"/api/investigations/{investigation['id']}/messages", json=body)
    assert hijack.status_code == 409


def test_aut_ca_16_first_uci_import_provisions_accounts_and_active_demo_links(uci_import):
    """AUT-CA-16: each imported Patient gets a demo account and ACTIVE link to the demo doctor."""
    from app.db.session import SessionLocal
    from app.models.entities import PatientDoctorLink

    snapshot = uci_import["first"]
    assert len(snapshot["patient_ids"]) == UCI_PATIENT_COUNT
    assert snapshot["demo_doctor"] is not None
    assert snapshot["record_sources"] == UCI_PATIENT_COUNT * UCI_DAYS * 4
    assert all(account is not None and account[4] is True for account in snapshot["accounts"])
    assert len({account[0] for account in snapshot["accounts"]}) == UCI_PATIENT_COUNT
    assert all(short_id and len(short_id) == 6 for short_id in snapshot["patient_short_ids"])
    demo_doctor_id = snapshot["demo_doctor"][0]
    with SessionLocal() as db:
        for patient_id, links in zip(snapshot["patient_ids"], snapshot["links"]):
            assert [status for _, status, _ in links] == ["ACTIVE"]
            assert db.get(PatientDoctorLink, links[0][0]).doctor_id == demo_doctor_id
    assert len(snapshot["demo_events"]) == UCI_PATIENT_COUNT


def test_aut_ca_17_second_import_is_idempotent(uci_import):
    """AUT-CA-17: re-running the import preserves counts, credentials, SHORTIDs and ids."""
    before = _uci_snapshot()
    after = uci_import["run"]()
    assert after == before
    assert after["record_sources"] == uci_import["first"]["record_sources"]
    assert after["patient_ids"] == uci_import["first"]["patient_ids"]
    assert after["patient_short_ids"] == uci_import["first"]["patient_short_ids"]


def test_aut_ca_17_reimport_does_not_reset_a_changed_demo_password(uci_import, world: World):
    """AUT-CA-17 / RF-17: a demo account whose password changed keeps it after re-import.

    Regression guard for finding A4 (REVISAO-FINAL.md): the importer used to
    rewrite ``password_hash`` back to the public demo password.
    """
    from app.core.crypto import hash_password
    from app.db.session import SessionLocal
    from app.models.entities import UserAccount

    account_id = uci_import["first"]["accounts"][1][0]
    new_password = world.new_password()
    with SessionLocal() as db:
        account = db.get(UserAccount, account_id)
        account.password_hash = hash_password(new_password)
        db.commit()
    with SessionLocal() as db:
        before = db.get(UserAccount, account_id)
        before_state = (bytes(before.email_encrypted), before.email_lookup, before.password_hash)
    uci_import["run"]()
    with SessionLocal() as db:
        after = db.get(UserAccount, account_id)
        assert (bytes(after.email_encrypted), after.email_lookup, after.password_hash) == before_state
    email = _demo_account_email(account_id)
    login = world.new_client().post("/api/auth/login", json={"email": email, "password": new_password})
    assert login.status_code == 200


def test_cscw_ca_11_reimport_neither_duplicates_events_nor_reactivates_revoked_links(uci_import, world: World):
    """CSCW-CA-11: reimport skips manually revoked links and does not duplicate events."""
    from app.db.session import SessionLocal
    from app.models.entities import PatientDoctorLink, ProvenanceEvent

    snapshot = _uci_snapshot()
    link_id, status, version = snapshot["links"][0][0]
    assert status == "ACTIVE"
    # Revoke through the domain service as the demo patient (same path as the API).
    from app.core.security import SessionPrincipal
    from app.models.entities import Patient, UserAccount
    from app.services.doctor_links import transition_link

    with SessionLocal() as db:
        patient = db.get(Patient, snapshot["patient_ids"][0])
        principal = SessionPrincipal(session=None, account=db.get(UserAccount, patient.user_account_id),
                                     patient=patient, doctor=None)
        transition_link(db, link_id, principal, "revoke", version, None)
    assert len(world.events("AssociationRevoked", link_id)) == 1
    events_before = world.count(ProvenanceEvent)

    after = uci_import["run"]()
    with SessionLocal() as db:
        stored = db.get(PatientDoctorLink, link_id)
        assert stored.status == "REVOKED"
    assert after["links"][0] == ((link_id, "REVOKED", version + 1),)
    assert after["demo_events"] == snapshot["demo_events"]
    assert len(world.events("AssociationRevoked", link_id)) == 1
    # The re-run adds only its own analytics/import bookkeeping, never association events.
    new_events = {e.activity_type for e in world.events()[events_before:]}
    assert not new_events & {"DemoAssociationProvisioned", "AssociationConfirmed", "AssociationRequested",
                             "AssociationRevoked"}, new_events


def test_cscw_ca_12_demo_provisioning_records_a_software_agent_not_a_human_acceptance(uci_import, world: World):
    """CSCW-CA-12: demo links are attributed to the importer SoftwareAgent.

    Assert DemoAssociationProvisioned exists with ActorKind/SoftwareAgent and
    that no AssociationConfirmed row pretends a human doctor accepted.
    """
    snapshot = uci_import["first"]
    demo_links = [links[0][0] for links in snapshot["links"]]
    events = world.events("DemoAssociationProvisioned")
    by_entity = {event.entity_id: event for event in events}
    for link_id in demo_links:
        event = by_entity[link_id]
        assert event.source_type == "software-agent"
        assert event.actor_user_id is None
        assert (event.metadata_json or {}).get("actor_kind") == "SoftwareImporter"
        assert world.events("AssociationConfirmed", link_id) == []
        assert world.events("AssociationRequested", link_id) == []


def test_aut_ca_21_recompute_preserves_indicators_and_readings(world: World):
    """AUT-CA-21: reprocessing the reference set keeps expected atypical days and readings."""
    from sqlalchemy import select

    from app.db.session import SessionLocal
    from app.models.entities import DailyIndicator, DailyMetricsCurrent, GlucoseRecord

    patient = world.patient()
    world.seed_readings(patient.id, days=10, extreme_offsets=(9,))

    def snapshot(run_id):
        with SessionLocal() as db:
            indicators = sorted(
                (i.indicator_date, bool(i.anomaly_flag), round(i.avg_glucose or 0, 6), i.glucose_event_count)
                for i in db.scalars(select(DailyIndicator).where(DailyIndicator.analysis_run_id == run_id)))
            metrics = sorted(
                (m.metric_date, round(m.avg_glucose or 0, 6), m.glucose_event_count)
                for m in db.scalars(select(DailyMetricsCurrent).where(DailyMetricsCurrent.patient_id == patient.id)))
            readings = sorted(
                (r.id, r.measured_at, r.glucose_mg_dl)
                for r in db.scalars(select(GlucoseRecord).where(GlucoseRecord.patient_id == patient.id)))
            return indicators, metrics, readings

    first = snapshot(world.compute(patient.id))
    second = snapshot(world.compute(patient.id))
    assert first == second
    atypical = {d for d, flag, _, _ in first[0] if flag}
    # The reference set has exactly one extreme day; it is the expected atypical day.
    assert atypical == {date(2026, 6, 10)}, atypical
    assert len(first[2]) == 10 * 5
    api_days = {row["date"] for row in patient.client.get(f"/api/patients/{patient.id}/atypical-days").json()["days"]}
    assert api_days == {d.isoformat() for d in atypical}


def test_aut_ca_21_uci_import_preserves_pre_timezone_anomaly_classification(uci_import, world: World):
    """The UCI import's UTC storage must preserve the former patient-local day buckets."""
    from app.core.patient_time import patient_local_datetime
    from app.db.session import SessionLocal
    from app.models.entities import DailyIndicator, GlucoseRecord, Patient
    from app.services.analytics import compute_analytics
    from sqlalchemy import select

    patient_id = uci_import["first"]["patient_ids"][0]
    with SessionLocal() as db:
        imported_patient = db.get(Patient, patient_id)
        imported_records = [(record.measured_at, record.glucose_mg_dl, record.context_label) for record in db.scalars(select(GlucoseRecord).where(
            GlucoseRecord.patient_id == patient_id,
        ).order_by(GlucoseRecord.measured_at))]
        timezone_name = imported_patient.timezone
        assert imported_records
        assert all(measured_at.hour in (11, 15, 21, 1) for measured_at, _, _ in imported_records)

    # Recreate the previous implementation's input contract: local wall times
    # were stored directly and grouped by their naive calendar date.
    baseline = world.patient()
    with SessionLocal() as db:
        baseline_profile = db.get(Patient, baseline.id)
        baseline_profile.timezone = "UTC"
        for measured_at, glucose, context in imported_records:
            wall_time = patient_local_datetime(measured_at, timezone_name).replace(tzinfo=None)
            db.add(GlucoseRecord(
                patient_id=baseline.id, measured_at=wall_time,
                glucose_mg_dl=glucose, context_label=context,
            ))
        db.commit()

    def atypical_dates(patient_key: str) -> set[date]:
        with SessionLocal() as db:
            run = compute_analytics(db, patient_id=patient_key, trigger_type="lote4-baseline")
            return set(db.scalars(select(DailyIndicator.indicator_date).where(
                DailyIndicator.analysis_run_id == run.id,
                DailyIndicator.anomaly_flag.is_(True),
            )).all())

    baseline_dates = atypical_dates(baseline.id)
    current_dates = atypical_dates(patient_id)
    assert current_dates == baseline_dates

    # Re-import is intentionally idempotent; it must not shift stored rows or
    # recompute a different clinical classification.
    uci_import["run"]()
    assert atypical_dates(patient_id) == baseline_dates


def test_cscw_ca_22_recompute_that_drops_the_flag_keeps_the_investigation_and_its_origin(world: World):
    """CSCW-CA-22: investigation survives reclassification with its historical origin."""
    from sqlalchemy import select, update

    from app.db.session import SessionLocal
    from app.models.entities import DailyIndicator, GlucoseRecord, Investigation, InvestigationMessage

    patient, prompts = world.atypical_patient()
    doctor = world.doctor()
    world.active_link(patient, doctor)
    origin = prompts[0]
    investigation = world.open_investigation(patient, doctor, event_id=origin["indicator_id"])
    reply = doctor.client.post(f"/api/investigations/{investigation['id']}/messages", json={"content": "Seen"})
    assert reply.status_code == 201
    origin_before = patient.client.get(f"/api/investigations/{investigation['id']}").json()["investigation"]["origin"]
    assert origin_before["indicator_id"] == origin["indicator_id"]
    assert origin_before["date"] == origin["date"]
    assert origin_before["analysis_run_id"]
    assert origin_before["is_current_classification"] is True

    # An empty patient-scoped execution is still the newest classification.
    from app.services.analytics import compute_analytics
    from app.services.reports import get_latest_patient_analytics_run

    with SessionLocal() as db:
        empty_run = compute_analytics(
            db, patient_id=patient.id, start_date=date(2026, 7, 1), end_date=date(2026, 7, 2),
            trigger_type="integration-empty-current-range",
        )
        assert empty_run.status == "completed"
        assert get_latest_patient_analytics_run(db, patient.id).id == empty_run.id
    after_empty_run = patient.client.get(f"/api/investigations/{investigation['id']}").json()["investigation"]["origin"]
    assert after_empty_run["indicator_id"] == origin_before["indicator_id"]
    assert after_empty_run["is_current_classification"] is False

    # Correct the readings of the flagged day so it is no longer atypical, then reprocess.
    flagged_day = date.fromisoformat(origin["date"])
    with SessionLocal() as db:
        db.execute(update(GlucoseRecord).where(
            GlucoseRecord.patient_id == patient.id,
            GlucoseRecord.measured_at >= datetime.combine(flagged_day, datetime.min.time()),
            GlucoseRecord.measured_at < datetime.combine(flagged_day + timedelta(days=1), datetime.min.time()),
        ).values(glucose_mg_dl=105.0))
        db.commit()
    new_run = world.compute(patient.id, trigger="integration-reclassify")

    with SessionLocal() as db:
        new_flag = db.scalar(select(DailyIndicator.anomaly_flag).where(
            DailyIndicator.analysis_run_id == new_run, DailyIndicator.indicator_date == flagged_day))
        assert not new_flag, "fixture did not drop the atypical flag"
        stored = db.get(Investigation, investigation["id"])
        assert stored.atypical_day_event_id == origin["indicator_id"]
        original = db.get(DailyIndicator, origin["indicator_id"])
        assert original is not None and original.anomaly_flag and original.indicator_date == flagged_day
        assert world.count(InvestigationMessage, InvestigationMessage.investigation_id == investigation["id"]) == 2
    detail = patient.client.get(f"/api/investigations/{investigation['id']}").json()
    assert detail["investigation"]["atypical_day_event_id"] == origin["indicator_id"]
    assert detail["investigation"]["origin"] == {
        **origin_before,
        "is_current_classification": False,
    }
    assert detail["investigation"]["status"] == "open"
    assert [m["content"] for m in detail["messages"]] == ["Initial message", "Seen"]
    doctor_detail = doctor.client.get(f"/api/investigations/{investigation['id']}")
    assert doctor_detail.status_code == 200
    assert doctor_detail.json()["investigation"]["origin"] == detail["investigation"]["origin"]
    listed = patient.client.get("/api/investigations").json()["investigations"]
    assert next(item for item in listed if item["id"] == investigation["id"])["origin"] == detail["investigation"]["origin"]


def test_cscw_ca_45_reimport_does_not_duplicate_historical_notices(uci_import):
    """CSCW-CA-45 (dedup half): repeated import runs add no prompt/notification and keep historical dates."""
    first = uci_import["first"]
    # Precondition for the consolidation test below: several historical atypical days per patient.
    assert all(len(prompts) >= 2 for prompts in first["prompts"].values()), first["prompts"]
    again = uci_import["run"]()
    assert again["prompts"] == first["prompts"]
    assert again["prompt_notifications"] == first["prompt_notifications"]
    today = date.today()
    for prompts in again["prompts"].values():
        for prompt_date, _ in prompts:
            assert date.fromisoformat(prompt_date) < today
            assert UCI_START <= date.fromisoformat(prompt_date) < UCI_START + timedelta(days=UCI_DAYS)


def test_cscw_ca_45_historical_import_notice_is_consolidated_and_deduplicated(uci_import):
    """CSCW-CA-45: two import runs produce one consolidated notice, never a flood.

    Regression guard for finding A9 (REVISAO-FINAL.md): one notification per
    patient per run, listing the historical dates, instead of one per day.
    """
    from sqlalchemy import select

    from app.db.session import SessionLocal
    from app.models.entities import Notification

    first = uci_import["first"]
    with SessionLocal() as db:
        for patient_id, account in zip(first["patient_ids"], first["accounts"]):
            notices = list(db.scalars(select(Notification).where(
                Notification.recipient_user_account_id == account[0],
                Notification.notification_type == "atypical_day_prompt")))
            assert len(notices) == 1, f"{len(notices)} atypical-day notifications for one imported patient"
            payload = notices[0].payload
            prompt_dates = sorted(d for d, _ in first["prompts"][patient_id])
            assert sorted(payload.get("dates", [])) == prompt_dates
            assert payload.get("count") == len(prompt_dates) >= 2


def test_aut_ca_21_recompute_handles_manual_readings_with_and_without_context(world: World):
    """AUT-CA-21 / NEW-1: recompute tolerates mixed string and NULL context labels."""
    from sqlalchemy import update

    from app.db.session import SessionLocal
    from app.models.entities import GlucoseRecord

    patient = world.patient()
    try:
        for index, label in enumerate(("pre_breakfast", None, "post_lunch", None, None)):
            body = {"measured_at": f"2026-06-0{index + 1}T08:00:00", "glucose_mg_dl": 100 + index}
            if label:
                body["context_label"] = label
            assert patient.client.post(f"/api/patients/{patient.id}/glucose-records", json=body).status_code == 201
        run_id = world.compute(patient.id)
        assert run_id
    finally:
        # Do not leave unlabelled rows behind: the module's global import analytics would trip on them.
        with SessionLocal() as db:
            db.execute(update(GlucoseRecord).where(
                GlucoseRecord.patient_id == patient.id, GlucoseRecord.context_label.is_(None),
            ).values(context_label="unspecified"))
            db.commit()
