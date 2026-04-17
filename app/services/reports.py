from __future__ import annotations

from datetime import date, timedelta
from math import ceil
from pathlib import Path
from statistics import mean
from urllib.parse import quote

from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from app.models.entities import AnalyticsRun, DailyIndicator, DataQualityIssue, ImportBatch, NormalizedEvent, Patient
from app.services.semantic import SAMPLE_QUERIES


def artifact_url(path: str | None) -> str | None:
    if not path:
        return None

    normalized = str(path).replace("\\", "/")
    try:
        if "/artifacts/" in normalized:
            relative_path = normalized.split("/artifacts/", 1)[1]
        elif normalized.startswith("artifacts/"):
            relative_path = normalized.split("artifacts/", 1)[1]
        else:
            artifact_path = Path(normalized)
            category = artifact_path.parent.name
            if not category:
                return None
            relative_path = f"{category}/{artifact_path.name}"

        relative_path = relative_path.lstrip("/")
        return f"/artifacts/{quote(relative_path, safe='/')}"
    except Exception:
        return None


def get_latest_import_batch(db: Session) -> ImportBatch | None:
    return db.scalars(select(ImportBatch).order_by(desc(ImportBatch.imported_at))).first()


def get_latest_analytics_run(db: Session) -> AnalyticsRun | None:
    return db.scalars(select(AnalyticsRun).order_by(desc(AnalyticsRun.started_at))).first()


def get_dashboard_summary(db: Session) -> dict[str, object]:
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
    }


def get_paginated_patients(
    db: Session,
    page: int = 1,
    page_size: int = 12,
    query: str | None = None,
) -> dict[str, object]:
    latest_run = get_latest_analytics_run(db)
    safe_page = max(page, 1)
    safe_page_size = max(1, min(page_size, 50))

    patient_query = select(Patient)
    if query:
        search = f"%{query.strip()}%"
        patient_query = patient_query.where(
            or_(
                Patient.display_name.ilike(search),
                Patient.source_file.ilike(search),
                Patient.source_patient_code.ilike(search),
            )
        )

    total = db.scalar(select(func.count()).select_from(patient_query.subquery())) or 0
    pages = max(1, ceil(total / safe_page_size)) if total else 1
    current_page = min(safe_page, pages)
    offset = (current_page - 1) * safe_page_size

    patients = db.scalars(
        patient_query.order_by(Patient.id).offset(offset).limit(safe_page_size)
    ).all()

    patient_rows: list[dict[str, object]] = []
    if patients:
        patient_ids = [patient.id for patient in patients]
        indicators_by_patient: dict[int, list[DailyIndicator]] = {}
        if latest_run:
            indicators = db.scalars(
                select(DailyIndicator)
                .where(DailyIndicator.analytics_run_id == latest_run.id, DailyIndicator.patient_id.in_(patient_ids))
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

    return {
        "patients": patient_rows,
        "count": total,
        "page": current_page,
        "page_size": safe_page_size,
        "pages": pages,
        "query": query or "",
    }


def _resolve_date_window(
    available_start: date | None,
    available_end: date | None,
    start_date: date | None,
    end_date: date | None,
    default_days: int = 30,
) -> tuple[date | None, date | None]:
    if available_start is None or available_end is None:
        return None, None

    resolved_end = min(end_date or available_end, available_end)
    if resolved_end < available_start:
        resolved_end = available_end

    default_start = max(available_start, resolved_end - timedelta(days=default_days - 1))
    resolved_start = max(start_date or default_start, available_start)

    if resolved_start > resolved_end:
        resolved_start = default_start

    return resolved_start, resolved_end


def _mean_or_none(values: list[float | None]) -> float | None:
    clean_values = [value for value in values if value is not None]
    return mean(clean_values) if clean_values else None


def _classify_cluster_profile(
    avg_glucose: float | None,
    pct_hypo: float | None,
    pct_in_range: float | None,
    pct_hyper: float | None,
    coefficient_of_variation: float | None,
) -> dict[str, str]:
    hypo = pct_hypo or 0.0
    in_range = pct_in_range or 0.0
    hyper = pct_hyper or 0.0
    avg = avg_glucose or 0.0
    cv = coefficient_of_variation or 0.0

    if hypo >= 15 and hyper < 35:
        return {
            "label": "Perfil com hipo frequente",
            "description": "Dias com maior concentração de leituras abaixo de 70 mg/dL.",
            "tone": "rose",
        }

    if hyper >= 60 or avg >= 220:
        return {
            "label": "Perfil hiper predominante",
            "description": "Dias marcados por predominância de leituras acima da meta.",
            "tone": "yellow",
        }

    if in_range >= 45 and hypo <= 10 and hyper <= 45 and cv <= 0.28:
        return {
            "label": "Perfil estável",
            "description": "Dias com maior permanência em faixa e menor variação glicêmica.",
            "tone": "green",
        }

    if cv >= 0.28 or (hypo >= 8 and hyper >= 30) or (hypo + hyper >= 55):
        return {
            "label": "Perfil variável",
            "description": "Dias com oscilação glicêmica mais acentuada ao longo do período.",
            "tone": "slate",
        }

    return {
        "label": "Perfil intermediário",
        "description": "Dias com comportamento misto, sem predominância clara de um padrão.",
        "tone": "blue",
    }


def _build_cluster_profile_map(indicators: list[DailyIndicator]) -> dict[int, dict[str, str]]:
    grouped: dict[int, list[DailyIndicator]] = {}
    for indicator in indicators:
        if indicator.cluster_label is None:
            continue
        grouped.setdefault(indicator.cluster_label, []).append(indicator)

    profile_map: dict[int, dict[str, str]] = {}
    for cluster_label, cluster_indicators in grouped.items():
        profile_map[cluster_label] = _classify_cluster_profile(
            avg_glucose=_mean_or_none([indicator.avg_glucose for indicator in cluster_indicators]),
            pct_hypo=_mean_or_none([indicator.pct_hypo for indicator in cluster_indicators]),
            pct_in_range=_mean_or_none([indicator.pct_in_range for indicator in cluster_indicators]),
            pct_hyper=_mean_or_none([indicator.pct_hyper for indicator in cluster_indicators]),
            coefficient_of_variation=_mean_or_none(
                [indicator.coefficient_of_variation for indicator in cluster_indicators]
            ),
        )

    return profile_map


def _serialize_indicator(
    indicator: DailyIndicator,
    cluster_profiles: dict[int, dict[str, str]] | None = None,
) -> dict[str, object]:
    cluster_profile = cluster_profiles.get(indicator.cluster_label) if cluster_profiles and indicator.cluster_label is not None else None
    return {
        "date": indicator.indicator_date.isoformat(),
        "avg_glucose": indicator.avg_glucose,
        "pct_hypo": indicator.pct_hypo,
        "pct_in_range": indicator.pct_in_range,
        "pct_hyper": indicator.pct_hyper,
        "anomaly_flag": indicator.anomaly_flag,
        "cluster_label": indicator.cluster_label,
        "cluster_profile_label": cluster_profile["label"] if cluster_profile else None,
        "cluster_profile_description": cluster_profile["description"] if cluster_profile else None,
        "cluster_profile_tone": cluster_profile["tone"] if cluster_profile else None,
        "low_events_count": indicator.low_events_count,
        "high_events_count": indicator.high_events_count,
    }


def _serialize_event(event: NormalizedEvent) -> dict[str, object]:
    return {
        "occurred_at": event.occurred_at.isoformat(),
        "event_date": event.event_date.isoformat(),
        "event_time": event.event_time.strftime("%H:%M"),
        "event_type": event.event_type,
        "event_subtype": event.event_subtype,
        "numeric_value": event.numeric_value,
        "glucose_mg_dl": event.glucose_mg_dl,
        "context_label": event.context_label,
        "timestamp_quality": event.timestamp_quality,
    }


def get_dashboard_context(db: Session) -> dict[str, object]:
    summary = get_dashboard_summary(db)
    patients_page = get_paginated_patients(db, page=1, page_size=70)
    semantic_query = SAMPLE_QUERIES["high_risk_days"]

    return {
        **summary,
        "patients": patients_page["patients"],
        "semantic_query": semantic_query,
        "semantic_result": [],
        "sample_queries": SAMPLE_QUERIES,
    }


def get_patient_detail_context(
    db: Session,
    patient_id: int,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict[str, object] | None:
    patient = db.get(Patient, patient_id)
    if patient is None:
        return None

    latest_batch = get_latest_import_batch(db)
    latest_run = get_latest_analytics_run(db)
    indicator_bounds = (
        db.execute(
            select(func.min(DailyIndicator.indicator_date), func.max(DailyIndicator.indicator_date)).where(
                DailyIndicator.analytics_run_id == latest_run.id,
                DailyIndicator.patient_id == patient_id,
            )
        ).one()
        if latest_run
        else (None, None)
    )
    event_bounds = db.execute(
        select(func.min(NormalizedEvent.event_date), func.max(NormalizedEvent.event_date)).where(
            NormalizedEvent.patient_id == patient_id,
            NormalizedEvent.is_glucose.is_(True),
        )
    ).one()
    available_start = indicator_bounds[0] or event_bounds[0]
    available_end = indicator_bounds[1] or event_bounds[1]
    resolved_start, resolved_end = _resolve_date_window(available_start, available_end, start_date, end_date)

    indicator_query = (
        select(DailyIndicator)
        .where(DailyIndicator.analytics_run_id == latest_run.id, DailyIndicator.patient_id == patient_id)
        .order_by(DailyIndicator.indicator_date)
        if latest_run
        else None
    )
    if indicator_query is not None and resolved_start and resolved_end:
        indicator_query = indicator_query.where(
            DailyIndicator.indicator_date >= resolved_start,
            DailyIndicator.indicator_date <= resolved_end,
        )
    indicators = db.scalars(indicator_query).all() if indicator_query is not None else []

    event_query = (
        select(NormalizedEvent)
        .where(NormalizedEvent.patient_id == patient_id)
        .order_by(desc(NormalizedEvent.occurred_at))
    )
    glucose_query = (
        select(NormalizedEvent)
        .where(NormalizedEvent.patient_id == patient_id, NormalizedEvent.is_glucose.is_(True))
        .order_by(NormalizedEvent.occurred_at)
    )
    if resolved_start and resolved_end:
        event_query = event_query.where(
            NormalizedEvent.event_date >= resolved_start,
            NormalizedEvent.event_date <= resolved_end,
        )
        glucose_query = glucose_query.where(
            NormalizedEvent.event_date >= resolved_start,
            NormalizedEvent.event_date <= resolved_end,
        )

    recent_events = db.scalars(event_query.limit(20)).all()
    glucose_events = db.scalars(glucose_query).all()
    quality_issues = db.scalars(
        select(DataQualityIssue)
        .where(DataQualityIssue.patient_id == patient_id)
        .order_by(desc(DataQualityIssue.created_at))
    ).all()

    avg_values = [indicator.avg_glucose for indicator in indicators if indicator.avg_glucose is not None]
    cluster_profiles = _build_cluster_profile_map(indicators)
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
    hourly_highs_250 = {hour: 0 for hour in range(24)}
    for event in glucose_events:
        if event.glucose_mg_dl is not None and event.glucose_mg_dl < 70:
            hourly_lows[event.event_time.hour] += 1
        if event.glucose_mg_dl is not None and event.glucose_mg_dl > 250:
            hourly_highs_250[event.event_time.hour] += 1

    return {
        "patient": patient,
        "latest_batch": latest_batch,
        "latest_run": latest_run,
        "filters": {
            "available_start_date": available_start.isoformat() if available_start else None,
            "available_end_date": available_end.isoformat() if available_end else None,
            "start_date": resolved_start.isoformat() if resolved_start else None,
            "end_date": resolved_end.isoformat() if resolved_end else None,
        },
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
        "hourly_highs_250": [{"hour": hour, "count": count} for hour, count in hourly_highs_250.items()],
        "cluster_profiles": cluster_profiles,
        "daily_indicators_json": [_serialize_indicator(indicator, cluster_profiles) for indicator in indicators],
        "glucose_events_json": [_serialize_event(event) for event in glucose_events],
        "recent_events_json": [_serialize_event(event) for event in recent_events],
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
