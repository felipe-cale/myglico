from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import AnalysisOutbox, DailyMetricsCurrent


def mark_analysis_pending(
    db: Session,
    patient_id: str,
    target_date: date,
    trigger_type: str,
) -> None:
    existing = db.scalar(
        select(AnalysisOutbox).where(
            AnalysisOutbox.patient_id == patient_id,
            AnalysisOutbox.start_date == target_date,
            AnalysisOutbox.end_date == target_date,
            AnalysisOutbox.status.in_(["pending", "processing"]),
        )
    )
    if existing is None:
        db.add(
            AnalysisOutbox(
                patient_id=patient_id,
                start_date=target_date,
                end_date=target_date,
                trigger_type=trigger_type,
            )
        )

    current = db.scalar(
        select(DailyMetricsCurrent).where(
            DailyMetricsCurrent.patient_id == patient_id,
            DailyMetricsCurrent.metric_date == target_date,
        )
    )
    if current is None:
        db.add(
            DailyMetricsCurrent(
                patient_id=patient_id,
                metric_date=target_date,
                freshness_status="stale",
            )
        )
    else:
        current.freshness_status = "stale"
        current.updated_at = datetime.utcnow()
