from __future__ import annotations

from datetime import date, datetime, time, timedelta
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
import platform
import subprocess

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.ensemble import IsolationForest
from sqlalchemy import and_, delete, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.patient_time import local_range_utc_bounds, patient_local_date, patient_local_datetime
from app.models.entities import AnalysisOutbox, AnalysisRun, DailyIndicator, DailyMetricsCurrent, GlucoseRecord, Patient, ProvenanceEvent
from app.services.daily_metrics import in_range as _in_range, upper_bound_for_context as _upper_bound_for_context
from app.services.investigations import create_prompts_for_indicators


settings = get_settings()


def _git_revision() -> str:
    try:
        return (
            subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL)
            .decode("utf-8")
            .strip()
        )
    except Exception:
        return "unknown"


def _package_version(package_name: str) -> str:
    try:
        return version(package_name)
    except PackageNotFoundError:
        return "unknown"


def _environment_snapshot() -> dict[str, object]:
    return {
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "database": settings.database_url.split(":", 1)[0],
        "library_versions": {
            "numpy": _package_version("numpy"),
            "pandas": _package_version("pandas"),
            "scikit_learn": _package_version("scikit-learn"),
            "sqlalchemy": _package_version("sqlalchemy"),
        },
    }


def _analysis_parameters() -> dict[str, object]:
    return {
        "hypo_threshold": settings.default_hypo_threshold,
        "pre_meal_range": [settings.pre_meal_min, settings.pre_meal_max],
        "post_meal_upper_bound": settings.post_meal_max,
        "generic_upper_bound": settings.generic_max,
        "anomaly_detector": {"name": "IsolationForest", "random_state": 42},
        "clustering": {"name": "KMeans", "max_clusters": 3, "random_state": 42},
    }


def _date_bounds(start_date: date | None, end_date: date | None) -> tuple[datetime | None, datetime | None]:
    if start_date is None or end_date is None:
        return None, None
    return datetime.combine(start_date, time.min), datetime.combine(end_date + timedelta(days=1), time.min)


def _records_fingerprint(records: list[GlucoseRecord]) -> str:
    digest = sha256()
    for record in sorted(records, key=lambda item: (item.patient_id, item.measured_at, item.id)):
        digest.update(
            "|".join(
                [
                    record.id,
                    record.patient_id,
                    record.measured_at.isoformat(),
                    str(record.glucose_mg_dl),
                    record.context_label or "",
                    record.updated_at.isoformat() if record.updated_at else "",
                ]
            ).encode("utf-8")
        )
    return digest.hexdigest()


def _payload_fingerprint(payload: object) -> str:
    return sha256(repr(payload).encode("utf-8")).hexdigest()


def _prepare_glucose_frame(
    records: list[GlucoseRecord], timezones: dict[str, str] | None = None,
) -> pd.DataFrame:
    if not records:
        return pd.DataFrame()

    frame = pd.DataFrame(
        [
            {
                "record_id": record.id,
                "patient_id": record.patient_id,
                "event_date": patient_local_date(record.measured_at, (timezones or {}).get(record.patient_id)),
                "event_time": patient_local_datetime(record.measured_at, (timezones or {}).get(record.patient_id)).time(),
                "context_label": record.context_label,
                "glucose_mg_dl": float(record.glucose_mg_dl),
            }
            for record in records
        ]
    )
    # pandas 3 may infer a nullable string column for mixed str/None values;
    # row-wise apply then receives NaN-like scalars. Keep explicit Python
    # strings/None so the context helpers have a stable input contract.
    frame["context_label"] = pd.Series(
        [record.context_label if isinstance(record.context_label, str) else None for record in records],
        index=frame.index,
        dtype=object,
    )
    frame["is_hypo"] = frame["glucose_mg_dl"] < settings.default_hypo_threshold
    frame["is_in_range"] = frame.apply(lambda row: _in_range(row["glucose_mg_dl"], row["context_label"]), axis=1)
    frame["is_hyper"] = frame.apply(
        lambda row: row["glucose_mg_dl"] >= _upper_bound_for_context(row["context_label"]) and not row["is_hypo"],
        axis=1,
    )
    frame["is_pre_meal"] = frame["context_label"].fillna("").str.startswith("pre_")
    frame["is_post_meal"] = frame["context_label"].fillna("").str.startswith("post_")
    frame["hour"] = frame["event_time"].apply(lambda value: value.hour)
    return frame


def _summary_rows_from_frame(frame: pd.DataFrame) -> list[dict[str, object]]:
    summary_rows: list[dict[str, object]] = []
    grouped = frame.groupby(["patient_id", "event_date"], sort=True)
    for (patient_id, indicator_date), group in grouped:
        pre_group = group[group["is_pre_meal"]]
        post_group = group[group["is_post_meal"]]
        avg = group["glucose_mg_dl"].mean()
        std = group["glucose_mg_dl"].std(ddof=0)
        summary_rows.append(
            {
                "patient_id": str(patient_id),
                "indicator_date": indicator_date,
                "glucose_event_count": int(len(group)),
                "avg_glucose": float(avg),
                "median_glucose": float(group["glucose_mg_dl"].median()),
                "min_glucose": float(group["glucose_mg_dl"].min()),
                "max_glucose": float(group["glucose_mg_dl"].max()),
                "std_glucose": float(std) if not np.isnan(std) else None,
                "coefficient_of_variation": float(std / avg) if avg else None,
                "pct_hypo": float(group["is_hypo"].mean() * 100.0),
                "pct_in_range": float(group["is_in_range"].mean() * 100.0),
                "pct_hyper": float(group["is_hyper"].mean() * 100.0),
                "pre_meal_in_range_pct": float(pre_group["is_in_range"].mean() * 100.0) if len(pre_group) else 0.0,
                "post_meal_in_range_pct": float(post_group["is_in_range"].mean() * 100.0) if len(post_group) else 0.0,
                "low_events_count": int(group["is_hypo"].sum()),
                "high_events_count": int(group["is_hyper"].sum()),
                "anomaly_score": None,
                "anomaly_flag": False,
                "cluster_label": None,
                "report_json": {
                    "hours_observed": sorted(group["hour"].astype(int).unique().tolist()),
                    "contexts": sorted([context for context in group["context_label"].dropna().unique().tolist() if context]),
                },
            }
        )
    return summary_rows


def _apply_advanced_analytics(summary_frame: pd.DataFrame) -> pd.DataFrame:
    if summary_frame.empty:
        return summary_frame

    for _, patient_frame in summary_frame.groupby("patient_id"):
        feature_columns = ["avg_glucose", "std_glucose", "pct_hypo", "pct_hyper", "glucose_event_count"]
        features = patient_frame[feature_columns].fillna(0.0)
        if len(patient_frame) >= 5:
            contamination = min(0.2, max(0.05, 1 / len(patient_frame)))
            detector = IsolationForest(random_state=42, contamination=contamination)
            detector.fit(features)
            summary_frame.loc[patient_frame.index, "anomaly_score"] = detector.decision_function(features)
            summary_frame.loc[patient_frame.index, "anomaly_flag"] = detector.predict(features) == -1
        if len(patient_frame) >= 3:
            cluster_count = min(3, len(patient_frame))
            kmeans = KMeans(n_clusters=cluster_count, n_init=10, random_state=42)
            summary_frame.loc[patient_frame.index, "cluster_label"] = kmeans.fit_predict(features)
    return summary_frame


def _upsert_daily_metrics(db: Session, rows: list[dict[str, object]], fingerprints_by_day: dict[tuple[str, date], str]) -> None:
    for row in rows:
        patient_id = str(row["patient_id"])
        metric_date = row["indicator_date"]
        current = db.scalar(
            select(DailyMetricsCurrent).where(
                DailyMetricsCurrent.patient_id == patient_id,
                DailyMetricsCurrent.metric_date == metric_date,
            )
        )
        values = {
            "glucose_event_count": row["glucose_event_count"],
            "avg_glucose": row["avg_glucose"],
            "min_glucose": row["min_glucose"],
            "max_glucose": row["max_glucose"],
            "pct_hypo": row["pct_hypo"],
            "pct_in_range": row["pct_in_range"],
            "pct_hyper": row["pct_hyper"],
            "low_events_count": row["low_events_count"],
            "high_events_count": row["high_events_count"],
            "freshness_status": "fresh",
            "input_fingerprint": fingerprints_by_day.get((patient_id, metric_date)),
            "updated_at": datetime.utcnow(),
        }
        if current is None:
            db.add(DailyMetricsCurrent(patient_id=patient_id, metric_date=metric_date, **values))
        else:
            for key, value in values.items():
                setattr(current, key, value)


def compute_analytics(
    db: Session,
    patient_id: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    trigger_type: str = "script",
) -> AnalysisRun:
    timezone_query = select(Patient.id, Patient.timezone)
    if patient_id:
        timezone_query = timezone_query.where(Patient.id == patient_id)
    timezones = dict(db.execute(timezone_query).all())
    query = select(GlucoseRecord).order_by(GlucoseRecord.patient_id, GlucoseRecord.measured_at, GlucoseRecord.id)
    if patient_id:
        query = query.where(GlucoseRecord.patient_id == patient_id)
    if start_date is not None and end_date is not None:
        patient_bounds = [
            and_(GlucoseRecord.patient_id == pid,
                 GlucoseRecord.measured_at >= local_range_utc_bounds(start_date, end_date, timezone)[0],
                 GlucoseRecord.measured_at < local_range_utc_bounds(start_date, end_date, timezone)[1])
            for pid, timezone in timezones.items()
        ]
        query = query.where(or_(*patient_bounds) if patient_bounds else False)

    records = db.scalars(query).all()
    input_fingerprint = _records_fingerprint(records)
    analysis_run = AnalysisRun(
        patient_id=patient_id,
        start_date=start_date,
        end_date=end_date,
        status="running",
        trigger_type=trigger_type,
        algorithm_name="daily_glycemic_summary",
        algorithm_version="v2",
        parameters_json=_analysis_parameters(),
        environment_json=_environment_snapshot(),
        code_version=_git_revision(),
        input_fingerprint=input_fingerprint,
    )
    db.add(analysis_run)
    db.flush()

    frame = _prepare_glucose_frame(records, timezones)
    if frame.empty:
        analysis_run.status = "completed"
        analysis_run.finished_at = datetime.utcnow()
        analysis_run.output_fingerprint = _payload_fingerprint([])
        db.add(
            ProvenanceEvent(
                activity_type="compute_daily_indicators",
                entity_type="analysis_run",
                entity_id=analysis_run.id,
                source_type="glucose_records",
                occurred_at=datetime.utcnow(),
                prov_json={
                    "activity": "compute_daily_indicators",
                    "used": "glucose_records",
                    "wasGeneratedBy": analysis_run.id,
                },
                metadata_json={"record_count": 0},
                content_hash=analysis_run.output_fingerprint,
            )
        )
        db.commit()
        db.refresh(analysis_run)
        return analysis_run

    summary_rows = _summary_rows_from_frame(frame)
    summary_frame = _apply_advanced_analytics(pd.DataFrame(summary_rows))
    rows = summary_frame.to_dict(orient="records")

    fingerprints_by_day: dict[tuple[str, date], str] = {}
    for (row_patient_id, event_date), group in frame.groupby(["patient_id", "event_date"], sort=True):
        day_records = [record for record in records if record.patient_id == row_patient_id and
                       patient_local_date(record.measured_at, timezones.get(str(row_patient_id))) == event_date]
        fingerprints_by_day[(str(row_patient_id), event_date)] = _records_fingerprint(day_records)

    _upsert_daily_metrics(db, rows, fingerprints_by_day)

    db.execute(delete(DailyIndicator).where(DailyIndicator.analysis_run_id == analysis_run.id))
    indicators = [DailyIndicator(analysis_run_id=analysis_run.id, **row) for row in rows]
    db.add_all(indicators)
    db.flush()
    create_prompts_for_indicators(db, indicators)

    outbox_query = select(AnalysisOutbox).where(AnalysisOutbox.status.in_(["pending", "processing"]))
    if patient_id:
        outbox_query = outbox_query.where(AnalysisOutbox.patient_id == patient_id)
    if start_date and end_date:
        outbox_query = outbox_query.where(AnalysisOutbox.start_date >= start_date, AnalysisOutbox.end_date <= end_date)
    for outbox_item in db.scalars(outbox_query).all():
        outbox_item.status = "completed"
        outbox_item.processed_at = datetime.utcnow()

    output_fingerprint = _payload_fingerprint(rows)
    analysis_run.status = "completed"
    analysis_run.finished_at = datetime.utcnow()
    analysis_run.output_fingerprint = output_fingerprint
    db.add(
        ProvenanceEvent(
            activity_type="compute_daily_indicators",
            entity_type="analysis_run",
            entity_id=analysis_run.id,
            source_type="glucose_records",
            occurred_at=datetime.utcnow(),
            prov_json={
                "entity": {"daily_indicators": {"prov:type": "mygv:DailyIndicatorSet"}},
                "activity": {"compute_daily_indicators": {"prov:type": "mygv:AnalyticsActivity"}},
                "used": {"compute_daily_indicators": "glucose_records"},
                "wasGeneratedBy": {"daily_indicators": "compute_daily_indicators"},
                "wasDerivedFrom": {"daily_indicators": "glucose_records"},
            },
            metadata_json={
                "input_fingerprint": input_fingerprint,
                "output_fingerprint": output_fingerprint,
                "record_count": len(records),
                "indicator_count": len(rows),
            },
            content_hash=output_fingerprint,
        )
    )
    db.commit()
    db.refresh(analysis_run)
    return analysis_run
