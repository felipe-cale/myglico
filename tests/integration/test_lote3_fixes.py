from __future__ import annotations

from datetime import date

from sqlalchemy import inspect, select


def test_a15_patient_identity_columns_are_non_nullable(world):
    from app.db.session import engine

    columns = {column["name"]: column for column in inspect(engine).get_columns("patients")}
    assert columns["name_encrypted"]["nullable"] is False
    assert columns["short_id"]["nullable"] is False


def test_o2_shared_ip_does_not_block_distinct_login_accounts():
    from app.core.rate_limit import consume, reset_for_tests

    reset_for_tests()
    try:
        for attempt in range(10):
            assert consume("login", "192.0.2.8", f"account-{attempt}@example.test")[0]
        assert consume("login", "192.0.2.8", "account-11@example.test")[0]
        for attempt in range(1, 10):
            assert consume("login", f"198.51.100.{attempt}", "account-0@example.test")[0]
        assert consume("login", "203.0.113.8", "account-0@example.test")[0] is False
    finally:
        reset_for_tests()


def test_o3_prompts_are_grouped_and_batch_defer_dismisses_all(world):
    from sqlalchemy import select

    from app.db.session import SessionLocal
    from app.models.entities import AtypicalDayPrompt, DailyIndicator
    from app.services.investigations import create_prompts_for_indicators

    patient, prompts = world.atypical_patient()
    extra_id = world.seed_indicator(patient.id, date(2026, 6, 20), anomaly=True)
    with SessionLocal() as db:
        create_prompts_for_indicators(db, [db.get(DailyIndicator, extra_id)])
        db.commit()
    grouped = patient.client.get(f"/api/patients/{patient.id}/atypical-day-prompts")
    assert grouped.status_code == 200
    batch = grouped.json()["prompts"]
    assert len(batch) == 1
    assert len(batch[0]["indicator_ids"]) >= 2
    assert batch[0]["dates"] == sorted(batch[0]["dates"])

    dismissed = patient.client.post("/api/atypical-day-prompts/defer", json={
        "indicator_ids": batch[0]["indicator_ids"],
    })
    assert dismissed.status_code == 200, dismissed.text
    assert {item["status"] for item in dismissed.json()["prompts"]} == {"deferred"}
    remaining = patient.client.get(f"/api/patients/{patient.id}/atypical-day-prompts").json()["prompts"]
    assert all(item["status"] == "deferred" for item in remaining)
    with SessionLocal() as db:
        rows = list(db.scalars(select(AtypicalDayPrompt).where(
            AtypicalDayPrompt.patient_id == patient.id,
        )))
        assert len(rows) == len(batch[0]["indicator_ids"])
        assert all(item.status == "DEFERRED" for item in rows)


def test_aut_ca_21_anomaly_classification_is_stable_across_crypto_protection(world):
    """Compare the clinical baseline with a full fresh encryption/blind-index pass."""
    from sqlalchemy import select

    from app.core.crypto import crm_uf_lookup, decrypt_field, email_lookup, encrypt_field
    from app.db.session import SessionLocal
    from app.models.entities import DailyIndicator, Doctor, Patient, UserAccount

    patient = world.patient()
    world.seed_readings(patient.id, days=10, extreme_offsets=(9,))

    def classifications(run_id):
        with SessionLocal() as db:
            return sorted(
                (row.indicator_date, bool(row.anomaly_flag))
                for row in db.scalars(select(DailyIndicator).where(
                    DailyIndicator.analysis_run_id == run_id,
                ))
            )

    baseline = classifications(world.compute(patient.id, trigger="before-crypto-protection"))
    expected = {day for day, anomalous in baseline if anomalous}
    assert expected == {date(2026, 6, 10)}

    with SessionLocal() as db:
        account = db.scalar(select(UserAccount).where(UserAccount.id == world.account_id(patient)))
        domain = db.get(Patient, patient.id)
        assert account is not None and domain is not None
        email = account.email
        account.email_encrypted = encrypt_field(
            email, table="user_accounts", column="email", record_id=account.id,
        )
        account.email_lookup = email_lookup(email)
        name = domain.name
        domain.name_encrypted = encrypt_field(
            name, table="patients", column="name", record_id=domain.id,
        )
        if domain.email is not None:
            domain.email_encrypted = encrypt_field(
                domain.email, table="patients", column="email", record_id=domain.id,
            )

        doctor = world.doctor()
        doctor_row = db.scalar(select(Doctor).where(Doctor.id == doctor.id))
        assert doctor_row is not None
        doctor_name = decrypt_field(doctor_row.name_encrypted, table="doctors", column="name", record_id=doctor_row.id)
        doctor_row.name_encrypted = encrypt_field(
            doctor_name, table="doctors", column="name", record_id=doctor_row.id,
        )
        crm = decrypt_field(doctor_row.crm_encrypted, table="doctors", column="crm", record_id=doctor_row.id)
        uf = decrypt_field(doctor_row.uf_encrypted, table="doctors", column="uf", record_id=doctor_row.id)
        doctor_row.crm_encrypted = encrypt_field(crm, table="doctors", column="crm", record_id=doctor_row.id)
        doctor_row.uf_encrypted = encrypt_field(uf, table="doctors", column="uf", record_id=doctor_row.id)
        doctor_row.crm_uf_lookup = crm_uf_lookup(crm, uf)
        db.commit()

    protected = classifications(world.compute(patient.id, trigger="after-crypto-protection"))
    assert protected == baseline
