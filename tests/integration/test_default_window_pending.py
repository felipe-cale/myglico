"""The default detail window must not open empty because the newest day is pending.

A manual reading after an older analysed history makes the newest available
day a pending one. Without explicit dates, the 30-day window ending there would
hold no analysed day, so the detail falls back to the 30 days ending at the
latest analysed day and reports the pending days left outside.
"""

from __future__ import annotations

from datetime import date, timedelta

from conftest import World
from test_manual_entry_daily_metrics import _detail, _post_reading, _seed_local_readings


def _analysed_patient(world: World):
    patient = world.patient()
    days = [date(2026, 6, 1) + timedelta(days=offset) for offset in range(10)]
    _seed_local_readings(patient.id, days, {date(2026, 6, 10): 480.0})
    world.compute(patient.id)
    return patient


def test_default_window_falls_back_to_the_latest_analysed_window(world: World):
    patient = _analysed_patient(world)
    _post_reading(patient, "2026-10-11T19:48:00", 110.0)

    body = _detail(patient)
    filters = body["filters"]
    assert filters["available_end_date"] == "2026-10-11"
    assert (filters["start_date"], filters["end_date"]) == ("2026-06-01", "2026-06-10")
    assert (filters["default_start_date"], filters["default_end_date"]) == ("2026-06-01", "2026-06-10")
    assert filters["window_fallback"] is True
    assert filters["pending_outside_window"] == 1
    assert filters["latest_pending_date"] == "2026-10-11"
    summary = body["summary"]
    assert summary["days_observed"] == 10
    assert summary["pending_analysis_days"] == 0
    assert summary["anomaly_days"] == 1
    assert all(row["analysis_pending"] is False for row in body["daily_indicators"])

    # Reloading the resolved window explicitly (the UI writes it to the URL) keeps the same notes.
    reloaded = _detail(patient, start_date="2026-06-01", end_date="2026-06-10")
    assert reloaded["filters"]["default_end_date"] == "2026-06-10"
    assert reloaded["filters"]["pending_outside_window"] == 1
    assert reloaded["filters"]["latest_pending_date"] == "2026-10-11"


def test_explicit_range_is_not_moved_by_the_fallback(world: World):
    patient = _analysed_patient(world)
    _post_reading(patient, "2026-10-11T19:48:00", 110.0)

    body = _detail(patient, start_date="2026-09-20", end_date="2026-10-11")
    filters = body["filters"]
    assert (filters["start_date"], filters["end_date"]) == ("2026-09-20", "2026-10-11")
    assert filters["pending_outside_window"] == 0
    assert body["summary"]["days_observed"] == 1
    assert body["summary"]["pending_analysis_days"] == 1

    only_end = _detail(patient, end_date="2026-10-11")
    assert only_end["filters"]["end_date"] == "2026-10-11"
    assert only_end["filters"]["start_date"] == "2026-09-12"


def test_default_window_with_analysed_days_keeps_its_pending_day(world: World):
    patient = _analysed_patient(world)
    _post_reading(patient, "2026-06-12T09:00:00", 200.0)

    body = _detail(patient)
    filters = body["filters"]
    assert (filters["start_date"], filters["end_date"]) == ("2026-06-01", "2026-06-12")
    assert filters["window_fallback"] is False
    assert filters["pending_outside_window"] == 0
    assert body["summary"]["days_observed"] == 11
    assert body["summary"]["pending_analysis_days"] == 1


def test_patient_with_only_pending_data_keeps_the_default_window(world: World):
    patient = world.patient()
    _post_reading(patient, "2026-10-11T19:48:00", 110.0)

    body = _detail(patient)
    filters = body["filters"]
    assert filters["start_date"] == filters["end_date"] == "2026-10-11"
    assert filters["default_end_date"] == "2026-10-11"
    assert filters["window_fallback"] is False
    assert filters["pending_outside_window"] == 0
    assert body["summary"]["days_observed"] == 1
    assert body["summary"]["pending_analysis_days"] == 1
