"""Basic per-day glycemic metrics computed in plain Python.

The API runtime (Vercel) cannot import numpy/pandas/scikit-learn, so the full
``compute_analytics`` pipeline only runs offline. A manual entry still needs the
day's basic indicators (count, mean, min/max, % hypo/in range/hyper) to be
correct immediately; this module recomputes them for a single patient-day using
the same range rules as ``app/services/analytics.py`` (which imports them from
here). Anomaly and cluster labels are not touched: the day stays ``stale`` in
``daily_metrics_current`` until the offline run consumes ``analysis_outbox``.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.patient_time import local_date_utc_bounds
from app.models.entities import DailyMetricsCurrent, GlucoseRecord


def upper_bound_for_context(context: str | None) -> float:
    settings = get_settings()
    if isinstance(context, str) and context.startswith("pre_"):
        return settings.pre_meal_max
    if isinstance(context, str) and context.startswith("post_"):
        return settings.post_meal_max
    return settings.generic_max


def in_range(glucose: float, context: str | None) -> bool:
    settings = get_settings()
    if glucose < settings.default_hypo_threshold:
        return False
    if isinstance(context, str) and context.startswith("pre_"):
        return settings.pre_meal_min <= glucose <= settings.pre_meal_max
    if isinstance(context, str) and context.startswith("post_"):
        return glucose < settings.post_meal_max
    return settings.default_hypo_threshold <= glucose <= settings.generic_max


def is_hypo(glucose: float) -> bool:
    return glucose < get_settings().default_hypo_threshold


def is_hyper(glucose: float, context: str | None) -> bool:
    return glucose >= upper_bound_for_context(context) and not is_hypo(glucose)


def basic_daily_values(readings: list[tuple[float, str | None]]) -> dict[str, object]:
    """Same basic fields ``_summary_rows_from_frame`` produces, without pandas."""
    count = len(readings)
    if count == 0:
        return {
            "glucose_event_count": 0,
            "avg_glucose": None,
            "min_glucose": None,
            "max_glucose": None,
            "pct_hypo": 0.0,
            "pct_in_range": 0.0,
            "pct_hyper": 0.0,
            "low_events_count": 0,
            "high_events_count": 0,
        }
    values = [float(glucose) for glucose, _ in readings]
    low = sum(1 for glucose, _ in readings if is_hypo(float(glucose)))
    high = sum(1 for glucose, context in readings if is_hyper(float(glucose), context))
    in_range_count = sum(1 for glucose, context in readings if in_range(float(glucose), context))
    return {
        "glucose_event_count": count,
        "avg_glucose": sum(values) / count,
        "min_glucose": min(values),
        "max_glucose": max(values),
        "pct_hypo": low / count * 100.0,
        "pct_in_range": in_range_count / count * 100.0,
        "pct_hyper": high / count * 100.0,
        "low_events_count": low,
        "high_events_count": high,
    }


def refresh_basic_daily_metrics(
    db: Session,
    patient_id: str,
    timezone_name: str | None,
    target_date: date,
) -> DailyMetricsCurrent:
    """Recompute the basic metrics of one patient-local day from its records.

    ``freshness_status`` is left as set by ``mark_analysis_pending``: the
    anomaly/cluster classification for the day is still pending offline.
    """
    db.flush()
    start, end = local_date_utc_bounds(target_date, timezone_name)
    readings = db.execute(
        select(GlucoseRecord.glucose_mg_dl, GlucoseRecord.context_label).where(
            GlucoseRecord.patient_id == patient_id,
            GlucoseRecord.measured_at >= start,
            GlucoseRecord.measured_at < end,
        )
    ).all()
    values = basic_daily_values([(row[0], row[1]) for row in readings])

    current = db.scalar(
        select(DailyMetricsCurrent).where(
            DailyMetricsCurrent.patient_id == patient_id,
            DailyMetricsCurrent.metric_date == target_date,
        )
    )
    if current is None:
        current = DailyMetricsCurrent(patient_id=patient_id, metric_date=target_date, freshness_status="stale")
        db.add(current)
    for key, value in values.items():
        setattr(current, key, value)
    current.updated_at = datetime.utcnow()
    return current
