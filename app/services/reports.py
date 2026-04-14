from __future__ import annotations

from pathlib import Path
from statistics import mean

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models.entities import AnalyticsRun, DailyIndicator, DataQualityIssue, ImportBatch, NormalizedEvent, Patient
from app.services.semantic import SAMPLE_QUERIES


def artifact_url(path: str | None) -> str | None:
    if not path:
        return None
    artifact_path = Path(path)
    try:
        category = artifact_path.parent.name
        return f"/artifacts/{category}/{artifact_path.name}"
    except Exception:
        return None


def get_latest_import_batch(db: Session) -> ImportBatch | None:
    return db.scalars(select(ImportBatch).order_by(desc(ImportBatch.imported_at))).first()


def get_latest_analytics_run(db: Session) -> AnalyticsRun | None:
    return db.scalars(select(AnalyticsRun).order_by(desc(AnalyticsRun.started_at))).first()


def get_dashboard_context(db: Session) -> dict[str, object]:
    latest_batch = get_latest_import_batch(db)
    latest_run = get_latest_analytics_run(db)
    patient_count = db.scalar(select(func.count(Patient.id))) or 0
    normalized_count = db.scalar(select(func.count(NormalizedEvent.id))) or 0
    issue_count = db.scalar(select(func.count(DataQualityIssue.id))) or 0
    indicator_count = (
        db.scalar(select(func.count(DailyIndicator.id)).where(DailyIndicator.analytics_run_id == latest_run.id))
        if latest_run
        else 0
    ) or 0

    patient_rows: list[dict[str, object]] = []
    patients = db.scalars(select(Patient).order_by(Patient.id)).all()
    indicators_by_patient: dict[int, list[DailyIndicator]] = {}
    if latest_run:
        indicators = db.scalars(
            select(DailyIndicator)
            .where(DailyIndicator.analytics_run_id == latest_run.id)
            .order_by(DailyIndicator.patient_id, DailyIndicator.indicator_date)
        ).all()
        for indicator in indicators:
            indicators_by_patient.setdefault(indicator.patient_id, []).append(indicator)

    for patient in patients:
        indicators = indicators_by_patient.get(patient.id, [])
        average_glucose = round(mean([row.avg_glucose for row in indicators if row.avg_glucose is not None]), 2) if indicators else None
        hypo_rate = round(mean([row.pct_hypo for row in indicators]), 2) if indicators else 0.0
        hyper_rate = round(mean([row.pct_hyper for row in indicators]), 2) if indicators else 0.0
        anomaly_days = sum(1 for row in indicators if row.anomaly_flag)
        patient_rows.append(
            {
                "id": patient.id,
                "display_name": patient.display_name,
                "source_file": patient.source_file,
                "days_observed": len(indicators),
                "avg_glucose": average_glucose,
                "pct_hypo": hypo_rate,
                "pct_hyper": hyper_rate,
                "anomaly_days": anomaly_days,
            }
        )

    semantic_query = SAMPLE_QUERIES["high_risk_days"]

    return {
        "latest_batch": latest_batch,
        "latest_run": latest_run,
        "latest_batch_links": {
            "provenance_json": artifact_url(latest_batch.provenance_json_path) if latest_batch else None,
            "provenance_ttl": artifact_url(latest_batch.provenance_ttl_path) if latest_batch else None,
        },
        "latest_run_links": {
            "provenance_json": artifact_url(latest_run.provenance_json_path) if latest_run else None,
            "provenance_ttl": artifact_url(latest_run.provenance_ttl_path) if latest_run else None,
            "semantic_ttl": artifact_url(latest_run.semantic_ttl_path) if latest_run else None,
        },
        "patient_count": patient_count,
        "normalized_count": normalized_count,
        "indicator_count": indicator_count,
        "issue_count": issue_count,
        "patients": patient_rows,
        "semantic_query": semantic_query,
        "semantic_result": [],
        "sample_queries": SAMPLE_QUERIES,
    }


def get_patient_detail_context(db: Session, patient_id: int) -> dict[str, object] | None:
    patient = db.get(Patient, patient_id)
    if patient is None:
        return None

    latest_batch = get_latest_import_batch(db)
    latest_run = get_latest_analytics_run(db)
    indicators = (
        db.scalars(
            select(DailyIndicator)
            .where(DailyIndicator.analytics_run_id == latest_run.id, DailyIndicator.patient_id == patient_id)
            .order_by(DailyIndicator.indicator_date)
        ).all()
        if latest_run
        else []
    )
    recent_events = db.scalars(
        select(NormalizedEvent)
        .where(NormalizedEvent.patient_id == patient_id)
        .order_by(desc(NormalizedEvent.occurred_at))
        .limit(20)
    ).all()
    glucose_events = db.scalars(
        select(NormalizedEvent)
        .where(NormalizedEvent.patient_id == patient_id, NormalizedEvent.is_glucose.is_(True))
        .order_by(NormalizedEvent.occurred_at)
    ).all()
    quality_issues = db.scalars(
        select(DataQualityIssue)
        .where(DataQualityIssue.patient_id == patient_id)
        .order_by(desc(DataQualityIssue.created_at))
    ).all()

    avg_values = [indicator.avg_glucose for indicator in indicators if indicator.avg_glucose is not None]
    summary = {
        "days_observed": len(indicators),
        "avg_glucose": round(mean(avg_values), 2) if avg_values else None,
        "pct_hypo": round(mean([indicator.pct_hypo for indicator in indicators]), 2) if indicators else 0.0,
        "pct_in_range": round(mean([indicator.pct_in_range for indicator in indicators]), 2) if indicators else 0.0,
        "pct_hyper": round(mean([indicator.pct_hyper for indicator in indicators]), 2) if indicators else 0.0,
        "anomaly_days": sum(1 for indicator in indicators if indicator.anomaly_flag),
        "glucose_measurements": len(glucose_events),
    }

    hourly_lows = {hour: 0 for hour in range(24)}
    for event in glucose_events:
        if event.glucose_mg_dl is not None and event.glucose_mg_dl < 70:
            hourly_lows[event.event_time.hour] += 1

    return {
        "patient": patient,
        "latest_batch": latest_batch,
        "latest_run": latest_run,
        "latest_batch_links": {
            "provenance_json": artifact_url(latest_batch.provenance_json_path) if latest_batch else None,
            "provenance_ttl": artifact_url(latest_batch.provenance_ttl_path) if latest_batch else None,
        },
        "latest_run_links": {
            "provenance_json": artifact_url(latest_run.provenance_json_path) if latest_run else None,
            "provenance_ttl": artifact_url(latest_run.provenance_ttl_path) if latest_run else None,
            "semantic_ttl": artifact_url(latest_run.semantic_ttl_path) if latest_run else None,
        },
        "summary": summary,
        "indicators": indicators,
        "recent_events": recent_events,
        "quality_issues": quality_issues,
        "hourly_lows": [{"hour": hour, "count": count} for hour, count in hourly_lows.items()],
        "line_chart_points": build_line_chart_points([indicator.avg_glucose or 0 for indicator in indicators]),
    }


def build_line_chart_points(values: list[float], width: int = 640, height: int = 220) -> str:
    if not values:
        return ""
    min_value = min(values)
    max_value = max(values)
    spread = max(max_value - min_value, 1.0)
    x_step = width / max(len(values) - 1, 1)
    points = []
    for index, value in enumerate(values):
        x_pos = round(index * x_step, 2)
        normalized = (value - min_value) / spread
        y_pos = round(height - (normalized * (height - 20)) - 10, 2)
        points.append(f"{x_pos},{y_pos}")
    return " ".join(points)
