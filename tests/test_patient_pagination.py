from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.base import Base
from app.models.entities import AnalysisRun, DailyIndicator, DailyMetricsCurrent, Patient
from app.services.reports import get_paginated_patients


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setenv("MYGLICO_ENCRYPTION_KEY_V1", "1" * 64)
    monkeypatch.setenv("MYGLICO_LOOKUP_HMAC_KEY", "2" * 64)
    get_settings.cache_clear()
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()
    get_settings.cache_clear()


def seed_patient(db, index, *, average=None, hypo=0, hyper=0):
    patient = Patient(id=f"patient-{index:03}", short_id=f"P{index:05}",
                      name=f"Demo Patient {index}", email=f"patient{index}@demo.invalid")
    db.add(patient)
    db.flush()
    if average is not None:
        for offset in range(3):
            db.add(DailyMetricsCurrent(patient_id=patient.id,
                metric_date=date(2026, 1, 1) + timedelta(days=offset),
                glucose_event_count=2, avg_glucose=average, pct_hypo=hypo, pct_hyper=hyper))
    db.commit()
    return patient.id


def test_database_pagination_bounds_queries_and_loaded_rows(db):
    ids = [seed_patient(db, i, average=120) for i in range(25)]
    db.expunge_all()
    statements, loaded = [], []

    def record_sql(*args):
        statements.append(args[2])

    def record_loaded(session, instance):
        loaded.append(instance)

    event.listen(db.bind, "before_cursor_execute", record_sql)
    event.listen(db, "loaded_as_persistent", record_loaded)
    try:
        result = get_paginated_patients(db, page=2, page_size=10, patient_ids=ids)
    finally:
        event.remove(db.bind, "before_cursor_execute", record_sql)
        event.remove(db, "loaded_as_persistent", record_loaded)

    assert result["count"] == 25 and result["pages"] == 3
    assert [row["id"] for row in result["patients"]] == ids[10:20]
    assert len(statements) == 5
    assert sum(isinstance(row, Patient) for row in loaded) == 10
    assert not any(isinstance(row, DailyMetricsCurrent) for row in loaded)
    assert all(row["days_observed"] == 3 for row in result["patients"])


def test_filters_scope_empty_metrics_and_page_clamping(db):
    stable = seed_patient(db, 1)
    high = seed_patient(db, 2, average=185, hypo=20)
    low = seed_patient(db, 3, average=120, hypo=10)
    seed_patient(db, 4, average=250)
    ids = [stable, high, low]
    assert get_paginated_patients(db, patient_ids=ids, signal="stable")["patients"][0]["avg_glucose"] is None
    assert [row["id"] for row in get_paginated_patients(db, patient_ids=ids, signal="attention")["patients"]] == [high]
    assert [row["id"] for row in get_paginated_patients(db, patient_ids=ids, signal="oscillation")["patients"]] == [low]
    result = get_paginated_patients(db, patient_ids=ids, query="PATIENT2@DEMO", page=99)
    assert result["count"] == 1 and result["page"] == 1
    assert result["patients"][0]["id"] == high
    assert get_paginated_patients(db, patient_ids=ids, query="P00003")["patients"][0]["id"] == low
    assert get_paginated_patients(db, patient_ids=ids, query="Patient 4")["count"] == 0
    assert get_paginated_patients(db, patient_ids=[])["patients"] == []


def test_anomaly_counts_keep_latest_patient_run_semantics(db):
    ids = [seed_patient(db, i) for i in range(3)]
    start = datetime(2026, 1, 1)
    old = AnalysisRun(id="global-old", status="completed", finished_at=start, created_at=start)
    db.add(old)
    db.flush()
    for patient_id in ids:
        db.add(DailyIndicator(analysis_run_id=old.id, patient_id=patient_id,
                             indicator_date=date(2026, 1, 1), anomaly_flag=True))
    db.add_all([
        AnalysisRun(id="empty-new", patient_id=ids[0], status="completed",
                    finished_at=start + timedelta(days=1), created_at=start),
        AnalysisRun(id="incomplete", patient_id=ids[1], status="running",
                    finished_at=start + timedelta(days=2), created_at=start),
        AnalysisRun(id="global-new", status="completed",
                    finished_at=start + timedelta(days=3), created_at=start),
    ])
    db.flush()
    db.add(DailyIndicator(analysis_run_id="global-new", patient_id=ids[2],
                         indicator_date=date(2026, 1, 1), anomaly_flag=False))
    db.commit()
    rows = get_paginated_patients(db, patient_ids=ids)["patients"]
    assert [row["anomaly_days"] for row in rows] == [0, 1, 0]
