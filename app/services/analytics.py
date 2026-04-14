from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.ensemble import IsolationForest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import AnalyticsRun, DailyIndicator, ImportBatch, NormalizedEvent


settings = get_settings()


def _upper_bound_for_context(context: str | None) -> float:
    if context and context.startswith("pre_"):
        return settings.pre_meal_max
    if context and context.startswith("post_"):
        return settings.post_meal_max
    return settings.generic_max


def _in_range(glucose: float, context: str | None) -> bool:
    if glucose < settings.default_hypo_threshold:
        return False
    if context and context.startswith("pre_"):
        return settings.pre_meal_min <= glucose <= settings.pre_meal_max
    if context and context.startswith("post_"):
        return glucose < settings.post_meal_max
    return settings.default_hypo_threshold <= glucose <= settings.generic_max


def _prepare_glucose_frame(db: Session, import_batch_id: str) -> pd.DataFrame:
    rows = db.execute(
        select(
            NormalizedEvent.id,
            NormalizedEvent.patient_id,
            NormalizedEvent.event_date,
            NormalizedEvent.event_time,
            NormalizedEvent.context_label,
            NormalizedEvent.glucose_mg_dl,
        ).where(
            NormalizedEvent.import_batch_id == import_batch_id,
            NormalizedEvent.is_glucose.is_(True),
            NormalizedEvent.glucose_mg_dl.is_not(None),
        )
    ).all()
    if not rows:
        return pd.DataFrame()

    frame = pd.DataFrame(rows, columns=["event_id", "patient_id", "event_date", "event_time", "context_label", "glucose_mg_dl"])
    frame["glucose_mg_dl"] = frame["glucose_mg_dl"].astype(float)
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


def compute_analytics(db: Session, import_batch: ImportBatch) -> AnalyticsRun:
    glucose_frame = _prepare_glucose_frame(db, import_batch.id)
    analytics_run = AnalyticsRun(
        import_batch_id=import_batch.id,
        version="v1",
        status="running",
        config_json={
            "hypo_threshold": settings.default_hypo_threshold,
            "pre_meal_range": [settings.pre_meal_min, settings.pre_meal_max],
            "post_meal_upper_bound": settings.post_meal_max,
            "generic_upper_bound": settings.generic_max,
        },
    )
    db.add(analytics_run)
    db.flush()

    if glucose_frame.empty:
        analytics_run.status = "completed"
        analytics_run.finished_at = datetime.utcnow()
        db.commit()
        db.refresh(analytics_run)
        return analytics_run

    summary_rows: list[dict[str, object]] = []
    grouped = glucose_frame.groupby(["patient_id", "event_date"], sort=True)
    for (patient_id, indicator_date), group in grouped:
        pre_group = group[group["is_pre_meal"]]
        post_group = group[group["is_post_meal"]]
        avg = group["glucose_mg_dl"].mean()
        median = group["glucose_mg_dl"].median()
        std = group["glucose_mg_dl"].std(ddof=0)
        cv = float(std / avg) if avg else None
        summary_rows.append(
            {
                "patient_id": int(patient_id),
                "indicator_date": indicator_date,
                "glucose_event_count": int(len(group)),
                "avg_glucose": float(avg),
                "median_glucose": float(median),
                "min_glucose": float(group["glucose_mg_dl"].min()),
                "max_glucose": float(group["glucose_mg_dl"].max()),
                "std_glucose": float(std) if not np.isnan(std) else None,
                "coefficient_of_variation": cv,
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

    summary_frame = pd.DataFrame(summary_rows)

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

    db.execute(delete(DailyIndicator).where(DailyIndicator.analytics_run_id == analytics_run.id))
    for row in summary_frame.to_dict(orient="records"):
        db.add(DailyIndicator(analytics_run_id=analytics_run.id, **row))

    analytics_run.status = "completed"
    analytics_run.finished_at = datetime.utcnow()
    db.commit()
    db.refresh(analytics_run)
    return analytics_run

