from __future__ import annotations

from datetime import date, datetime, time, timedelta
from math import ceil
from pathlib import Path
from statistics import mean
from urllib.parse import quote

from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.patient_time import local_range_utc_bounds, patient_local_date, patient_local_datetime
from app.models.entities import (
    AnalysisRun,
    DailyIndicator,
    DailyMetricsCurrent,
    DataQualityIssue,
    GlucoseRecord,
    ImportBatch,
    Patient,
    ProvenanceArtifact,
)


EVENT_TYPE_LABELS = {
    "glucose_measurement": "Medição de glicose",
    "insulin_dose": "Dose de insulina",
    "symptom": "Sintoma",
    "meal": "Alimentação",
    "exercise": "Exercício",
    "special_event": "Evento especial",
    "unknown": "Desconhecido",
}

EVENT_SUBTYPE_LABELS = {
    "regular": "Insulina regular",
    "nph": "Insulina NPH",
    "ultralente": "Insulina ultralente",
    "unspecified": "Não especificado",
    "pre_breakfast": "Antes do café da manhã",
    "post_breakfast": "Após o café da manhã",
    "pre_lunch": "Antes do almoço",
    "post_lunch": "Após o almoço",
    "pre_supper": "Antes do jantar",
    "post_supper": "Após o jantar",
    "pre_snack": "Antes do lanche",
    "hypoglycemic_symptom": "Sintoma de hipoglicemia",
    "typical_meal": "Refeição usual",
    "more_than_usual_meal": "Refeição acima do usual",
    "less_than_usual_meal": "Refeição abaixo do usual",
    "typical_exercise": "Exercício usual",
    "more_than_usual_exercise": "Exercício acima do usual",
    "less_than_usual_exercise": "Exercício abaixo do usual",
    "unspecified_special_event": "Evento especial não especificado",
    "unknown": "Desconhecido",
}

CONTEXT_LABELS = {
    "unspecified": "Sem contexto informado",
    "pre_breakfast": "Antes do café da manhã",
    "post_breakfast": "Após o café da manhã",
    "pre_lunch": "Antes do almoço",
    "post_lunch": "Após o almoço",
    "pre_supper": "Antes do jantar",
    "post_supper": "Após o jantar",
    "pre_snack": "Antes do lanche",
}

TIMESTAMP_QUALITY_LABELS = {
    "recorded": "Registrado",
    "slot_aligned": "Ajustado ao horário padrão",
    "inferred": "Inferido",
    "estimated": "Estimado",
    "invalid": "Inválido",
    "missing": "Ausente",
    "unknown": "Desconhecido",
}


def _humanize_enum_value(value: str | None) -> str:
    if not value:
        return "-"
    return " ".join(part.capitalize() for part in str(value).split("_") if part)


def _enum_label(value: str | None, labels: dict[str, str]) -> str:
    if not value:
        return "-"
    return labels.get(value, _humanize_enum_value(value))


def _patient_signal(avg_glucose: float | None, pct_hypo: float | None, pct_hyper: float | None) -> dict[str, str]:
    avg_value = avg_glucose or 0.0
    hypo_value = pct_hypo or 0.0
    hyper_value = pct_hyper or 0.0

    if hyper_value >= 65 or avg_value >= 185:
        return {"code": "attention", "label": "Perfil Hiperglicêmico", "tone": "alert"}
    if hypo_value >= 10:
        return {"code": "oscillation", "label": "Perfil Hipoglicêmico", "tone": "warning"}
    return {"code": "stable", "label": "Perfil em Faixa", "tone": "stable"}


def _record_timestamp_quality(record: GlucoseRecord) -> str:
    for source in record.sources:
        metadata = source.metadata_json or {}
        timestamp_quality = metadata.get("timestamp_quality")
        if timestamp_quality:
            return str(timestamp_quality)
    return "recorded"


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


def _artifact_path(
    db: Session,
    owner_type: str,
    owner_id: str,
    artifact_type: str,
    artifact_format: str | None = None,
) -> str | None:
    query = select(ProvenanceArtifact).where(
        ProvenanceArtifact.owner_type == owner_type,
        ProvenanceArtifact.owner_id == owner_id,
        ProvenanceArtifact.artifact_type == artifact_type,
        ProvenanceArtifact.status == "completed",
    )
    if artifact_format:
        query = query.where(ProvenanceArtifact.format == artifact_format)
    artifact = db.scalars(query.order_by(desc(ProvenanceArtifact.created_at))).first()
    return artifact.path if artifact else None


def get_latest_import_batch(db: Session) -> ImportBatch | None:
    return db.scalars(select(ImportBatch).order_by(desc(ImportBatch.started_at))).first()


def get_latest_analytics_run(db: Session) -> AnalysisRun | None:
    return db.scalars(select(AnalysisRun).order_by(desc(AnalysisRun.started_at))).first()


def get_latest_patient_analytics_run(db: Session, patient_id: str) -> AnalysisRun | None:
    """Get the newest completed run owned by or containing this patient.

    Dataset imports may create global AnalysisRuns (patient_id is NULL), so
    include output rows for those runs. Patient-scoped runs with no output are
    still authoritative: they represent a newer analysis with no classified
    dates and must not leave an older result looking current.
    """
    return db.scalars(
        select(AnalysisRun)
        .where(
            AnalysisRun.status == "completed",
            or_(
                AnalysisRun.patient_id == patient_id,
                select(DailyIndicator.id).where(
                    DailyIndicator.analysis_run_id == AnalysisRun.id,
                    DailyIndicator.patient_id == patient_id,
                ).exists(),
            ),
        )
        .order_by(AnalysisRun.finished_at.desc(), AnalysisRun.created_at.desc())
    ).first()


def get_dashboard_summary(db: Session) -> dict[str, object]:
    latest_batch = get_latest_import_batch(db)
    latest_run = get_latest_analytics_run(db)
    patient_count = db.scalar(select(func.count(Patient.id))) or 0
    glucose_count = db.scalar(select(func.count(GlucoseRecord.id))) or 0
    issue_count = db.scalar(select(func.count(DataQualityIssue.id))) or 0
    indicator_count = (
        db.scalar(select(func.count(DailyIndicator.id)).where(DailyIndicator.analysis_run_id == latest_run.id))
        if latest_run
        else 0
    ) or 0

    latest_batch_links = {"provenance_json": None, "provenance_ttl": None}
    if latest_batch:
        latest_batch_links = {
            "provenance_json": artifact_url(_artifact_path(db, "import_batch", latest_batch.id, "provenance", "json")),
            "provenance_ttl": artifact_url(_artifact_path(db, "import_batch", latest_batch.id, "provenance", "ttl")),
        }

    latest_run_links = {"provenance_json": None, "provenance_ttl": None}
    if latest_run:
        latest_run_links = {
            "provenance_json": artifact_url(_artifact_path(db, "analysis_run", latest_run.id, "provenance", "json")),
            "provenance_ttl": artifact_url(_artifact_path(db, "analysis_run", latest_run.id, "provenance", "ttl")),
        }

    return {
        "latest_batch": latest_batch,
        "latest_run": latest_run,
        "latest_batch_links": latest_batch_links,
        "latest_run_links": latest_run_links,
        "patient_count": patient_count,
        "normalized_count": glucose_count,
        "indicator_count": indicator_count,
        "issue_count": issue_count,
    }


def get_paginated_patients(
    db: Session,
    page: int = 1,
    page_size: int = 12,
    query: str | None = None,
    signal: str | None = None,
    patient_id: str | None = None,
    patient_ids: list[str] | None = None,
) -> dict[str, object]:
    safe_page = max(page, 1)
    safe_page_size = max(1, min(page_size, 50))
    normalized_signal = (signal or "all").strip().lower()
    normalized_query = (query or "").strip().lower()

    # Patient.name is decrypted at the application boundary and is not a SQL
    # column; order by the stable internal key rather than ciphertext.
    patient_query = select(Patient).order_by(Patient.id)
    if patient_id is not None:
        patient_query = patient_query.where(Patient.id == patient_id)
    if patient_ids is not None:
        patient_query = patient_query.where(Patient.id.in_(patient_ids))
    patients = db.scalars(patient_query).all()

    patient_rows: list[dict[str, object]] = []
    if patients:
        patient_ids = [patient.id for patient in patients]
        metrics_by_patient: dict[str, list[DailyMetricsCurrent]] = {}
        metrics = db.scalars(
            select(DailyMetricsCurrent)
            .where(DailyMetricsCurrent.patient_id.in_(patient_ids))
            .order_by(DailyMetricsCurrent.patient_id, DailyMetricsCurrent.metric_date)
        ).all()
        for metric in metrics:
            metrics_by_patient.setdefault(metric.patient_id, []).append(metric)

        anomaly_by_patient: dict[str, int] = {}
        for patient in patients:
            patient_run = get_latest_patient_analytics_run(db, patient.id)
            if patient_run is not None:
                anomaly_by_patient[patient.id] = int(db.scalar(
                    select(func.count(DailyIndicator.id)).where(
                        DailyIndicator.analysis_run_id == patient_run.id,
                        DailyIndicator.patient_id == patient.id,
                        DailyIndicator.anomaly_flag.is_(True),
                    )
                ) or 0)

        for patient in patients:
            patient_metrics = metrics_by_patient.get(patient.id, [])
            average_glucose = (
                round(mean([row.avg_glucose for row in patient_metrics if row.avg_glucose is not None]), 2)
                if patient_metrics
                else None
            )
            hypo_rate = round(mean([row.pct_hypo for row in patient_metrics]), 2) if patient_metrics else 0.0
            hyper_rate = round(mean([row.pct_hyper for row in patient_metrics]), 2) if patient_metrics else 0.0
            patient_signal = _patient_signal(average_glucose, hypo_rate, hyper_rate)
            patient_rows.append(
                {
                    "id": patient.id,
                    "short_id": patient.short_id,
                    "display_name": patient.name,
                    "name": patient.name,
                    "email": patient.email,
                    "source_file": patient.source_file,
                    "days_observed": len(patient_metrics),
                    "avg_glucose": average_glucose,
                    "pct_hypo": hypo_rate,
                    "pct_hyper": hyper_rate,
                    "anomaly_days": anomaly_by_patient.get(patient.id, 0),
                    "signal_code": patient_signal["code"],
                    "signal_label": patient_signal["label"],
                    "signal_tone": patient_signal["tone"],
                }
            )

    if normalized_query:
        patient_rows = [
            row
            for row in patient_rows
            if normalized_query in (row["display_name"] or "").lower()
            or normalized_query in (row["email"] or "").lower()
            or normalized_query in str(row["short_id"]).lower()
        ]

    if normalized_signal != "all":
        patient_rows = [row for row in patient_rows if row["signal_code"] == normalized_signal]

    total = len(patient_rows)
    pages = max(1, ceil(total / safe_page_size)) if total else 1
    current_page = min(safe_page, pages)
    offset = (current_page - 1) * safe_page_size
    paginated_rows = patient_rows[offset : offset + safe_page_size]

    return {
        "patients": paginated_rows,
        "count": total,
        "page": current_page,
        "page_size": safe_page_size,
        "pages": pages,
        "query": query or "",
        "signal": normalized_signal,
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


def _stale_metric_dates(db: Session, patient_id: str) -> set[date]:
    """Days whose readings changed after the latest analysis (still pending)."""
    return set(db.scalars(
        select(DailyMetricsCurrent.metric_date).where(
            DailyMetricsCurrent.patient_id == patient_id,
            DailyMetricsCurrent.freshness_status != "fresh",
        )
    ))


def _resolve_default_window(
    db: Session,
    patient_id: str,
    latest_run: AnalysisRun | None,
    available_start: date | None,
    available_end: date | None,
    stale_dates: set[date],
) -> tuple[date | None, date | None, bool]:
    """Default window, anchored on analysed data when the newest days are pending.

    With no explicit dates the window ends at the newest available day. When
    that 30-day window holds only days still waiting for analysis (e.g. a
    manual reading after an older analysed history), it would open empty, so
    it ends at the latest analysed day instead (third value ``True``).
    """
    resolved_start, resolved_end = _resolve_date_window(available_start, available_end, None, None)
    if latest_run is None or resolved_start is None or resolved_end is None:
        return resolved_start, resolved_end, False
    analysed_dates = [
        day for day in db.scalars(
            select(DailyIndicator.indicator_date).where(
                DailyIndicator.analysis_run_id == latest_run.id,
                DailyIndicator.patient_id == patient_id,
            )
        )
        if day not in stale_dates
    ]
    if not analysed_dates or any(resolved_start <= day <= resolved_end for day in analysed_dates):
        return resolved_start, resolved_end, False
    fallback_start, fallback_end = _resolve_date_window(available_start, available_end, None, max(analysed_dates))
    return fallback_start, fallback_end, True


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
        return {"code": "hipo_frequente", "label": "Perfil com hipo frequente", "description": "Dias com mais leituras abaixo de 70 mg/dL.", "tone": "rose"}
    if hyper >= 60 or avg >= 220:
        return {"code": "hiper_predominante", "label": "Perfil hiper predominante", "description": "Dias com predominancia de leituras acima da meta.", "tone": "yellow"}
    if in_range >= 45 and hypo <= 10 and hyper <= 45 and cv <= 0.28:
        return {"code": "estavel", "label": "Perfil estavel", "description": "Dias com maior permanencia em faixa e menor variacao.", "tone": "green"}
    if cv >= 0.28 or (hypo >= 8 and hyper >= 30) or (hypo + hyper >= 55):
        return {"code": "variavel", "label": "Perfil variavel", "description": "Dias com oscilacao glicemica mais acentuada.", "tone": "slate"}
    return {"code": "intermediario", "label": "Perfil intermediario", "description": "Dias com comportamento misto.", "tone": "blue"}


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
            coefficient_of_variation=_mean_or_none([indicator.coefficient_of_variation for indicator in cluster_indicators]),
        )
    return profile_map


def _merge_daily_rows(
    indicators: list[DailyIndicator],
    metrics: list[DailyMetricsCurrent],
) -> list[DailyIndicator | DailyMetricsCurrent]:
    """Per-day rows for the summary: analysed indicators, except stale days.

    A day marked stale (e.g. by a manual entry) changed after the latest
    analysis run, so its basic values come from ``daily_metrics_current``
    (recomputed in the API transaction) and its anomaly/cluster classification
    is pending. Without any indicator, every metric day is used, as before.
    """
    if not indicators:
        return list(metrics)
    stale_by_date = {metric.metric_date: metric for metric in metrics if metric.freshness_status != "fresh"}
    rows: dict[date, DailyIndicator | DailyMetricsCurrent] = {
        indicator.indicator_date: indicator for indicator in indicators
    }
    rows.update(stale_by_date)
    return [rows[day] for day in sorted(rows)]


def _summarize_daily_rows(
    rows: list[DailyIndicator | DailyMetricsCurrent],
    glucose_measurements: int,
) -> dict[str, object]:
    avg_values = [row.avg_glucose for row in rows if row.avg_glucose is not None]
    return {
        "days_observed": len(rows),
        "avg_glucose": round(mean(avg_values), 2) if avg_values else None,
        "pct_hypo": round(mean([row.pct_hypo for row in rows]), 2) if rows else 0.0,
        "pct_in_range": round(mean([row.pct_in_range for row in rows]), 2) if rows else 0.0,
        "pct_hyper": round(mean([row.pct_hyper for row in rows]), 2) if rows else 0.0,
        # Only analysed, up-to-date days can be atypical; pending days are counted apart.
        "anomaly_days": sum(1 for row in rows if isinstance(row, DailyIndicator) and row.anomaly_flag),
        "pending_analysis_days": sum(1 for row in rows if isinstance(row, DailyMetricsCurrent) and row.freshness_status != "fresh"),
        "glucose_measurements": glucose_measurements,
    }


def _serialize_daily_rows(
    rows: list[DailyIndicator | DailyMetricsCurrent],
    cluster_profiles: dict[int, dict[str, str]],
) -> list[dict[str, object]]:
    return [
        _serialize_indicator(row, cluster_profiles) if isinstance(row, DailyIndicator) else _serialize_metric(row)
        for row in rows
    ]


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
        "cluster_profile_code": cluster_profile["code"] if cluster_profile else None,
        "cluster_profile_label": cluster_profile["label"] if cluster_profile else None,
        "cluster_profile_description": cluster_profile["description"] if cluster_profile else None,
        "cluster_profile_tone": cluster_profile["tone"] if cluster_profile else None,
        "low_events_count": indicator.low_events_count,
        "high_events_count": indicator.high_events_count,
        "analysis_pending": False,
    }


def _serialize_metric(metric: DailyMetricsCurrent) -> dict[str, object]:
    return {
        "date": metric.metric_date.isoformat(),
        "avg_glucose": metric.avg_glucose,
        "pct_hypo": metric.pct_hypo,
        "pct_in_range": metric.pct_in_range,
        "pct_hyper": metric.pct_hyper,
        "anomaly_flag": False,
        "cluster_label": None,
        "cluster_profile_code": None,
        "cluster_profile_label": None,
        "cluster_profile_description": None,
        "cluster_profile_tone": None,
        "low_events_count": metric.low_events_count,
        "high_events_count": metric.high_events_count,
        "analysis_pending": metric.freshness_status != "fresh",
    }


def _serialize_record(record: GlucoseRecord, timezone_name: str | None = None) -> dict[str, object]:
    event_type = "glucose_measurement"
    event_subtype = record.context_label
    context_label = record.context_label
    timestamp_quality = _record_timestamp_quality(record)

    local_datetime = patient_local_datetime(record.measured_at, timezone_name)
    return {
        "occurred_at": local_datetime.isoformat(),
        "event_date": local_datetime.date().isoformat(),
        "event_time": local_datetime.strftime("%H:%M"),
        "event_type": event_type,
        "event_type_label": _enum_label(event_type, EVENT_TYPE_LABELS),
        "event_subtype": event_subtype,
        "event_subtype_label": _enum_label(event_subtype, EVENT_SUBTYPE_LABELS),
        "numeric_value": record.glucose_mg_dl,
        "glucose_mg_dl": record.glucose_mg_dl,
        "context_label": context_label,
        "context_label_display": _enum_label(context_label, CONTEXT_LABELS),
        "timestamp_quality": timestamp_quality,
        "timestamp_quality_label": _enum_label(timestamp_quality, TIMESTAMP_QUALITY_LABELS),
    }


def _serialize_report_record(record: GlucoseRecord, timezone_name: str | None = None) -> dict[str, object]:
    event_type = "glucose_measurement"
    event_subtype = record.context_label
    context_label = record.context_label
    local_datetime = patient_local_datetime(record.measured_at, timezone_name)
    return {
        "occurred_at": local_datetime.isoformat(),
        "event_date": local_datetime.date().isoformat(),
        "event_time": local_datetime.strftime("%H:%M"),
        "event_type": event_type,
        "event_type_label": _enum_label(event_type, EVENT_TYPE_LABELS),
        "event_subtype": event_subtype,
        "event_subtype_label": _enum_label(event_subtype, EVENT_SUBTYPE_LABELS),
        "numeric_value": record.glucose_mg_dl,
        "glucose_mg_dl": record.glucose_mg_dl,
        "context_label": context_label,
        "context_label_display": _enum_label(context_label, CONTEXT_LABELS),
    }


def get_patient_detail_context(
    db: Session,
    patient_id: str,
    start_date: date | None = None,
    end_date: date | None = None,
    exact_dates: list[date] | None = None,
    *, indicator_page: int = 1, indicator_page_size: int = 10,
    event_page: int = 1, event_page_size: int = 10,
) -> dict[str, object] | None:
    patient = db.get(Patient, patient_id)
    if patient is None:
        return None

    latest_batch = get_latest_import_batch(db)
    latest_run = get_latest_patient_analytics_run(db, patient_id)
    metric_bounds = db.execute(
        select(func.min(DailyMetricsCurrent.metric_date), func.max(DailyMetricsCurrent.metric_date)).where(
            DailyMetricsCurrent.patient_id == patient_id,
        )
    ).one()
    record_bounds = db.execute(
        select(func.min(GlucoseRecord.measured_at), func.max(GlucoseRecord.measured_at)).where(
            GlucoseRecord.patient_id == patient_id,
        )
    ).one()
    record_start = patient_local_date(record_bounds[0], patient.timezone) if record_bounds[0] else None
    record_end = patient_local_date(record_bounds[1], patient.timezone) if record_bounds[1] else None
    available_start = metric_bounds[0] or record_start
    available_end = metric_bounds[1] or record_end
    stale_dates = _stale_metric_dates(db, patient_id)
    default_start, default_end, window_fallback = _resolve_default_window(
        db, patient_id, latest_run, available_start, available_end, stale_dates,
    )
    if exact_dates is not None:
        # Exact selection is authoritative, including dates outside the default
        # or explicitly requested interval.
        resolved_start, resolved_end = None, None
    elif start_date is None and end_date is None:
        resolved_start, resolved_end = default_start, default_end
    else:
        resolved_start, resolved_end = _resolve_date_window(available_start, available_end, start_date, end_date)
    # Pending days newer than the window are reported apart, so a window that
    # ends before them (e.g. the analysed fallback) still says they exist.
    pending_after = sorted(day for day in stale_dates if resolved_end and day > resolved_end)

    indicator_query = None
    if latest_run:
        indicator_query = (
            select(DailyIndicator)
            .where(DailyIndicator.analysis_run_id == latest_run.id, DailyIndicator.patient_id == patient_id)
            .order_by(DailyIndicator.indicator_date)
        )
        if resolved_start and resolved_end:
            indicator_query = indicator_query.where(
                DailyIndicator.indicator_date >= resolved_start,
                DailyIndicator.indicator_date <= resolved_end,
            )
        if exact_dates is not None:
            indicator_query = indicator_query.where(DailyIndicator.indicator_date.in_(exact_dates))
    indicators = db.scalars(indicator_query).all() if indicator_query is not None else []

    metric_query = select(DailyMetricsCurrent).where(DailyMetricsCurrent.patient_id == patient_id).order_by(DailyMetricsCurrent.metric_date)
    if resolved_start and resolved_end:
        metric_query = metric_query.where(
            DailyMetricsCurrent.metric_date >= resolved_start,
            DailyMetricsCurrent.metric_date <= resolved_end,
        )
    if exact_dates is not None:
        metric_query = metric_query.where(DailyMetricsCurrent.metric_date.in_(exact_dates))
    metrics = db.scalars(metric_query).all()

    record_query = (
        select(GlucoseRecord)
        .options(selectinload(GlucoseRecord.sources))
        .where(GlucoseRecord.patient_id == patient_id)
        .order_by(desc(GlucoseRecord.measured_at))
    )
    glucose_query = (
        select(GlucoseRecord)
        .options(selectinload(GlucoseRecord.sources))
        .where(GlucoseRecord.patient_id == patient_id)
        .order_by(GlucoseRecord.measured_at)
    )
    if resolved_start and resolved_end:
        start_dt, end_dt = local_range_utc_bounds(resolved_start, resolved_end, patient.timezone)
        record_query = record_query.where(GlucoseRecord.measured_at >= start_dt, GlucoseRecord.measured_at < end_dt)
        glucose_query = glucose_query.where(GlucoseRecord.measured_at >= start_dt, GlucoseRecord.measured_at < end_dt)
    if exact_dates is not None:
        local_bounds = [local_range_utc_bounds(day, day, patient.timezone) for day in exact_dates]
        exact_filter = or_(*[
            (GlucoseRecord.measured_at >= start) & (GlucoseRecord.measured_at < end)
            for start, end in local_bounds
        ])
        record_query = record_query.where(exact_filter)
        glucose_query = glucose_query.where(exact_filter)

    recent_total = db.scalar(select(func.count()).select_from(record_query.order_by(None).subquery())) or 0
    recent_pages = max(1, (recent_total + event_page_size - 1) // event_page_size)
    current_event_page = min(max(event_page, 1), recent_pages)
    recent_records = db.scalars(record_query.order_by(GlucoseRecord.measured_at.desc(), GlucoseRecord.id)
        .offset((current_event_page - 1) * event_page_size).limit(event_page_size)).all()
    glucose_records = db.scalars(glucose_query).all()
    quality_issues = db.scalars(
        select(DataQualityIssue)
        .where(DataQualityIssue.patient_id == patient_id)
        .order_by(desc(DataQualityIssue.created_at))
        .limit(50)
    ).all()

    daily_rows = _merge_daily_rows(indicators, metrics)
    summary = _summarize_daily_rows(daily_rows, len(glucose_records))

    hourly_lows = {hour: 0 for hour in range(24)}
    hourly_highs_250 = {hour: 0 for hour in range(24)}
    for record in glucose_records:
        local_hour = patient_local_datetime(record.measured_at, patient.timezone).hour
        if record.glucose_mg_dl < 70:
            hourly_lows[local_hour] += 1
        if record.glucose_mg_dl > 250:
            hourly_highs_250[local_hour] += 1

    cluster_profiles = _build_cluster_profile_map(indicators)
    daily_indicators_json = _serialize_daily_rows(daily_rows, cluster_profiles)
    indicator_total = len(daily_indicators_json)
    indicator_pages = max(1, (indicator_total + indicator_page_size - 1) // indicator_page_size)
    current_indicator_page = min(max(indicator_page, 1), indicator_pages)
    indicator_offset = (current_indicator_page - 1) * indicator_page_size
    freshness_status = "fresh"
    if any(getattr(metric, "freshness_status", "fresh") != "fresh" for metric in metrics):
        freshness_status = "updating"

    latest_batch_links = {"provenance_json": None, "provenance_ttl": None}
    if latest_batch:
        latest_batch_links = {
            "provenance_json": artifact_url(_artifact_path(db, "import_batch", latest_batch.id, "provenance", "json")),
            "provenance_ttl": artifact_url(_artifact_path(db, "import_batch", latest_batch.id, "provenance", "ttl")),
        }
    latest_run_links = {"provenance_json": None, "provenance_ttl": None}
    if latest_run:
        latest_run_links = {
            "provenance_json": artifact_url(_artifact_path(db, "analysis_run", latest_run.id, "provenance", "json")),
            "provenance_ttl": artifact_url(_artifact_path(db, "analysis_run", latest_run.id, "provenance", "ttl")),
        }

    return {
        "patient": patient,
        "latest_batch": latest_batch,
        "latest_run": latest_run,
        "filters": {
            "available_start_date": available_start.isoformat() if available_start else None,
            "available_end_date": available_end.isoformat() if available_end else None,
            "start_date": resolved_start.isoformat() if resolved_start else None,
            "end_date": resolved_end.isoformat() if resolved_end else None,
            "default_start_date": default_start.isoformat() if default_start else None,
            "default_end_date": default_end.isoformat() if default_end else None,
            "window_fallback": window_fallback,
            "pending_outside_window": len(pending_after),
            "latest_pending_date": pending_after[-1].isoformat() if pending_after else None,
        },
        "latest_batch_links": latest_batch_links,
        "latest_run_links": latest_run_links,
        "analytics_status": freshness_status,
        "summary": summary,
        "indicators": indicators,
        "recent_events": recent_records,
        "quality_issues": quality_issues,
        "hourly_lows": [{"hour": hour, "count": count} for hour, count in hourly_lows.items()],
        "hourly_highs_250": [{"hour": hour, "count": count} for hour, count in hourly_highs_250.items()],
        "cluster_profiles": cluster_profiles,
        "daily_indicators_json": daily_indicators_json,
        "daily_indicators_page_json": daily_indicators_json[indicator_offset:indicator_offset + indicator_page_size],
        "daily_indicators_pagination": {
            "page": current_indicator_page, "page_size": indicator_page_size,
            "total": indicator_total, "pages": indicator_pages,
        },
        "glucose_events_json": [_serialize_record(record, patient.timezone) for record in glucose_records],
        "recent_events_json": [_serialize_record(record, patient.timezone) for record in recent_records],
        "recent_events_pagination": {
            "page": current_event_page, "page_size": event_page_size,
            "total": recent_total, "pages": recent_pages,
        },
        "line_chart_points": build_line_chart_points([row.get("avg_glucose") or 0 for row in daily_indicators_json]),
    }


def get_patient_report_context(
    db: Session,
    patient_id: str,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict[str, object] | None:
    patient = db.get(Patient, patient_id)
    if patient is None:
        return None

    latest_run = get_latest_patient_analytics_run(db, patient_id)
    metric_bounds = db.execute(
        select(func.min(DailyMetricsCurrent.metric_date), func.max(DailyMetricsCurrent.metric_date)).where(
            DailyMetricsCurrent.patient_id == patient_id,
        )
    ).one()
    record_bounds = db.execute(
        select(func.min(GlucoseRecord.measured_at), func.max(GlucoseRecord.measured_at)).where(
            GlucoseRecord.patient_id == patient_id,
        )
    ).one()
    record_start = patient_local_date(record_bounds[0], patient.timezone) if record_bounds[0] else None
    record_end = patient_local_date(record_bounds[1], patient.timezone) if record_bounds[1] else None
    available_start = metric_bounds[0] or record_start
    available_end = metric_bounds[1] or record_end
    if start_date is None and end_date is None:
        resolved_start, resolved_end, _ = _resolve_default_window(
            db, patient_id, latest_run, available_start, available_end, _stale_metric_dates(db, patient_id),
        )
    else:
        resolved_start, resolved_end = _resolve_date_window(available_start, available_end, start_date, end_date)

    indicator_query = None
    if latest_run:
        indicator_query = (
            select(DailyIndicator)
            .where(DailyIndicator.analysis_run_id == latest_run.id, DailyIndicator.patient_id == patient_id)
            .order_by(DailyIndicator.indicator_date)
        )
        if resolved_start and resolved_end:
            indicator_query = indicator_query.where(
                DailyIndicator.indicator_date >= resolved_start,
                DailyIndicator.indicator_date <= resolved_end,
            )
    indicators = db.scalars(indicator_query).all() if indicator_query is not None else []

    metric_query = select(DailyMetricsCurrent).where(DailyMetricsCurrent.patient_id == patient_id).order_by(DailyMetricsCurrent.metric_date)
    if resolved_start and resolved_end:
        metric_query = metric_query.where(
            DailyMetricsCurrent.metric_date >= resolved_start,
            DailyMetricsCurrent.metric_date <= resolved_end,
        )
    metrics = db.scalars(metric_query).all()

    glucose_query = select(GlucoseRecord).where(GlucoseRecord.patient_id == patient_id).order_by(GlucoseRecord.measured_at)
    if resolved_start and resolved_end:
        start_dt, end_dt = local_range_utc_bounds(resolved_start, resolved_end, patient.timezone)
        glucose_query = glucose_query.where(GlucoseRecord.measured_at >= start_dt, GlucoseRecord.measured_at < end_dt)
    glucose_records = db.scalars(glucose_query).all()

    daily_rows = _merge_daily_rows(indicators, metrics)
    summary = _summarize_daily_rows(daily_rows, len(glucose_records))

    cluster_profiles = _build_cluster_profile_map(indicators)
    daily_indicators_json = _serialize_daily_rows(daily_rows, cluster_profiles)

    return {
        "patient": patient,
        "filters": {
            "available_start_date": available_start.isoformat() if available_start else None,
            "available_end_date": available_end.isoformat() if available_end else None,
            "start_date": resolved_start.isoformat() if resolved_start else None,
            "end_date": resolved_end.isoformat() if resolved_end else None,
        },
        "summary": summary,
        "daily_indicators_json": daily_indicators_json,
        "glucose_events_json": [_serialize_report_record(record, patient.timezone) for record in glucose_records],
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
