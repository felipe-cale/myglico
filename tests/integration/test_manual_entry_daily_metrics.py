"""D2: a manual reading must show up in the detail's daily indicators at once.

The API cannot run the pandas/sklearn analytics, so the manual-entry
transaction recomputes only the day's basic metrics; the anomaly/cluster
classification stays pending in ``analysis_outbox`` until the offline run.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from conftest import World


def _seed_local_readings(patient_id: str, days: list[date], values_by_day: dict[date, float]) -> None:
    """Readings at local wall times, so each one lands on the intended patient day."""
    from app.core.patient_time import local_datetime_to_utc_naive
    from app.db.session import SessionLocal
    from app.models.entities import GlucoseRecord, Patient

    with SessionLocal() as db:
        timezone_name = db.get(Patient, patient_id).timezone
        for day in days:
            for hour in (7, 10, 13, 16, 19):
                db.add(GlucoseRecord(
                    patient_id=patient_id,
                    measured_at=local_datetime_to_utc_naive(datetime.combine(day, datetime.min.time()) + timedelta(hours=hour), timezone_name),
                    glucose_mg_dl=values_by_day.get(day, 105.0),
                    context_label="unspecified",
                ))
        db.commit()


def _post_reading(patient, measured_at: str, value: float, context_label: str = "unspecified") -> None:
    response = patient.client.post(
        f"/api/patients/{patient.id}/glucose-records",
        json={"measured_at": measured_at, "glucose_mg_dl": value, "context_label": context_label},
    )
    assert response.status_code == 201, response.text


def _detail(patient, **params) -> dict:
    response = patient.client.get(f"/api/patients/{patient.id}", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_manual_reading_on_a_day_without_data_fills_the_daily_indicators(world: World):
    from sqlalchemy import select

    from app.db.session import SessionLocal
    from app.models.entities import AnalysisOutbox, DailyMetricsCurrent

    patient = world.patient()
    _post_reading(patient, "2026-10-11T19:48:00", 110.0)

    body = _detail(patient)
    assert body["filters"]["start_date"] == body["filters"]["end_date"] == "2026-10-11"
    summary = body["summary"]
    assert summary["days_observed"] == 1
    assert summary["avg_glucose"] == 110.0
    assert (summary["pct_hypo"], summary["pct_in_range"], summary["pct_hyper"]) == (0.0, 100.0, 0.0)
    assert summary["glucose_measurements"] == 1
    assert summary["anomaly_days"] == 0
    assert summary["pending_analysis_days"] == 1
    assert body["analytics_status"] == "updating"

    [day] = body["daily_indicators"]
    assert day["date"] == "2026-10-11"
    assert day["avg_glucose"] == 110.0
    assert (day["pct_hypo"], day["pct_in_range"], day["pct_hyper"]) == (0.0, 100.0, 0.0)
    assert day["analysis_pending"] is True
    assert day["cluster_label"] is None

    with SessionLocal() as db:
        metric = db.scalar(select(DailyMetricsCurrent).where(DailyMetricsCurrent.patient_id == patient.id))
        assert metric.metric_date == date(2026, 10, 11)
        assert metric.glucose_event_count == 1
        assert (metric.min_glucose, metric.max_glucose) == (110.0, 110.0)
        assert (metric.low_events_count, metric.high_events_count) == (0, 0)
        assert metric.freshness_status == "stale"
        outbox = list(db.scalars(select(AnalysisOutbox).where(AnalysisOutbox.patient_id == patient.id)))
        assert [(item.start_date, item.status) for item in outbox] == [(date(2026, 10, 11), "pending")]


def test_second_manual_reading_on_the_same_day_updates_the_ranges(world: World):
    patient = world.patient()
    _post_reading(patient, "2026-10-11T08:00:00", 60.0)
    _post_reading(patient, "2026-10-11T12:00:00", 250.0, context_label="post_lunch")
    _post_reading(patient, "2026-10-11T19:48:00", 110.0)

    body = _detail(patient, dates="2026-10-11")
    summary = body["summary"]
    assert summary["days_observed"] == 1
    assert summary["glucose_measurements"] == 3
    assert summary["avg_glucose"] == pytest.approx((60 + 250 + 110) / 3, abs=0.01)
    assert summary["pct_hypo"] == pytest.approx(33.33, abs=0.01)
    assert summary["pct_in_range"] == pytest.approx(33.33, abs=0.01)
    assert summary["pct_hyper"] == pytest.approx(33.33, abs=0.01)
    [day] = body["daily_indicators"]
    assert (day["low_events_count"], day["high_events_count"]) == (1, 1)


def test_manual_reading_on_an_analysed_day_replaces_its_stale_indicator(world: World):
    patient = world.patient()
    days = [date(2026, 6, 1) + timedelta(days=offset) for offset in range(10)]
    _seed_local_readings(patient.id, days, {date(2026, 6, 10): 480.0})
    world.compute(patient.id)

    before = _detail(patient, start_date="2026-06-01", end_date="2026-06-10")
    assert before["summary"]["days_observed"] == 10
    assert before["summary"]["pending_analysis_days"] == 0
    assert before["summary"]["anomaly_days"] == 1
    analysed = {row["date"]: row for row in before["daily_indicators"]}
    assert analysed["2026-06-05"]["avg_glucose"] == 105.0

    _post_reading(patient, "2026-06-05T21:00:00", 45.0)

    after = _detail(patient, start_date="2026-06-01", end_date="2026-06-10")
    rows = {row["date"]: row for row in after["daily_indicators"]}
    assert len(rows) == 10
    changed = rows["2026-06-05"]
    assert changed["analysis_pending"] is True
    assert changed["avg_glucose"] == pytest.approx((5 * 105 + 45) / 6)
    assert changed["pct_hypo"] == pytest.approx(100 / 6, abs=1e-3)
    assert changed["pct_in_range"] == pytest.approx(500 / 6, abs=1e-3)
    assert changed["low_events_count"] == 1
    # Untouched days keep their analysed classification, including the atypical one.
    assert rows["2026-06-10"]["analysis_pending"] is False and rows["2026-06-10"]["anomaly_flag"] is True
    assert after["summary"]["anomaly_days"] == 1
    assert after["summary"]["pending_analysis_days"] == 1
    assert after["summary"]["glucose_measurements"] == 51

    # A new day inside an analysed window is no longer dropped from the summary.
    _post_reading(patient, "2026-06-11T09:00:00", 200.0)
    extended = _detail(patient, start_date="2026-06-01", end_date="2026-06-11")
    assert extended["summary"]["days_observed"] == 11
    assert extended["summary"]["pending_analysis_days"] == 2
    new_day = {row["date"]: row for row in extended["daily_indicators"]}["2026-06-11"]
    assert new_day["avg_glucose"] == 200.0 and new_day["pct_hyper"] == 100.0

    # The offline run consumes the outbox and the days become analysed again.
    world.compute(patient.id)
    final = _detail(patient, start_date="2026-06-01", end_date="2026-06-11")
    assert final["summary"]["pending_analysis_days"] == 0
    assert final["analytics_status"] == "fresh"
    final_rows = {row["date"]: row for row in final["daily_indicators"]}
    assert final_rows["2026-06-05"]["analysis_pending"] is False
    assert final_rows["2026-06-05"]["avg_glucose"] == pytest.approx(changed["avg_glucose"])
    assert final_rows["2026-06-05"]["pct_hypo"] == pytest.approx(changed["pct_hypo"])
    assert final_rows["2026-06-11"]["avg_glucose"] == 200.0
