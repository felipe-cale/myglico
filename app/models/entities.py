from __future__ import annotations

from datetime import date, datetime, time
from uuid import uuid4

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _uuid() -> str:
    return str(uuid4())


class ImportBatch(Base):
    __tablename__ = "import_batches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    source_name: Mapped[str] = mapped_column(String(120), nullable=False)
    source_url: Mapped[str] = mapped_column(String(500), nullable=False)
    source_version: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(40), default="completed", nullable=False)
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    raw_record_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    normalized_record_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    provenance_json_path: Mapped[str | None] = mapped_column(String(500))
    provenance_ttl_path: Mapped[str | None] = mapped_column(String(500))
    notes: Mapped[str | None] = mapped_column(Text)

    raw_events: Mapped[list["RawEvent"]] = relationship(back_populates="import_batch", cascade="all, delete-orphan")
    normalized_events: Mapped[list["NormalizedEvent"]] = relationship(back_populates="import_batch", cascade="all, delete-orphan")
    quality_issues: Mapped[list["DataQualityIssue"]] = relationship(back_populates="import_batch", cascade="all, delete-orphan")
    analytics_runs: Mapped[list["AnalyticsRun"]] = relationship(back_populates="import_batch", cascade="all, delete-orphan")


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_patient_code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    source_file: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    raw_events: Mapped[list["RawEvent"]] = relationship(back_populates="patient")
    normalized_events: Mapped[list["NormalizedEvent"]] = relationship(back_populates="patient")
    daily_indicators: Mapped[list["DailyIndicator"]] = relationship(back_populates="patient")
    quality_issues: Mapped[list["DataQualityIssue"]] = relationship(back_populates="patient")


class RawEvent(Base):
    __tablename__ = "raw_events"
    __table_args__ = (UniqueConstraint("patient_id", "source_line", name="uq_raw_event_patient_line"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    import_batch_id: Mapped[str] = mapped_column(ForeignKey("import_batches.id"), nullable=False, index=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), nullable=False, index=True)
    source_file: Mapped[str] = mapped_column(String(120), nullable=False)
    source_line: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_date: Mapped[str] = mapped_column(String(20), nullable=False)
    raw_time: Mapped[str] = mapped_column(String(10), nullable=False)
    raw_code: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_value: Mapped[str] = mapped_column(String(40), nullable=False)
    raw_payload: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    import_batch: Mapped["ImportBatch"] = relationship(back_populates="raw_events")
    patient: Mapped["Patient"] = relationship(back_populates="raw_events")
    normalized_event: Mapped["NormalizedEvent"] = relationship(back_populates="raw_event", uselist=False)


class NormalizedEvent(Base):
    __tablename__ = "normalized_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    import_batch_id: Mapped[str] = mapped_column(ForeignKey("import_batches.id"), nullable=False, index=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), nullable=False, index=True)
    raw_event_id: Mapped[int] = mapped_column(ForeignKey("raw_events.id"), nullable=False, unique=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    event_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    event_time: Mapped[time] = mapped_column(Time, nullable=False)
    event_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    event_subtype: Mapped[str | None] = mapped_column(String(80))
    numeric_value: Mapped[float | None] = mapped_column(Float)
    glucose_mg_dl: Mapped[float | None] = mapped_column(Float)
    insulin_units: Mapped[float | None] = mapped_column(Float)
    context_label: Mapped[str | None] = mapped_column(String(80), index=True)
    meal_size: Mapped[str | None] = mapped_column(String(40))
    exercise_level: Mapped[str | None] = mapped_column(String(40))
    symptom_label: Mapped[str | None] = mapped_column(String(120))
    special_event_label: Mapped[str | None] = mapped_column(String(120))
    is_glucose: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    matches_slot_time: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    timestamp_quality: Mapped[str] = mapped_column(String(40), nullable=False)
    quality_note: Mapped[str | None] = mapped_column(Text)
    provenance_artifact: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    import_batch: Mapped["ImportBatch"] = relationship(back_populates="normalized_events")
    patient: Mapped["Patient"] = relationship(back_populates="normalized_events")
    raw_event: Mapped["RawEvent"] = relationship(back_populates="normalized_event")


class AnalyticsRun(Base):
    __tablename__ = "analytics_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    import_batch_id: Mapped[str] = mapped_column(ForeignKey("import_batches.id"), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(40), nullable=False, default="v1")
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="completed")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    config_json: Mapped[dict | None] = mapped_column(JSON)
    provenance_json_path: Mapped[str | None] = mapped_column(String(500))
    provenance_ttl_path: Mapped[str | None] = mapped_column(String(500))
    semantic_ttl_path: Mapped[str | None] = mapped_column(String(500))

    import_batch: Mapped["ImportBatch"] = relationship(back_populates="analytics_runs")
    indicators: Mapped[list["DailyIndicator"]] = relationship(back_populates="analytics_run", cascade="all, delete-orphan")


class DailyIndicator(Base):
    __tablename__ = "daily_indicators"
    __table_args__ = (UniqueConstraint("analytics_run_id", "patient_id", "indicator_date", name="uq_indicator_day"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    analytics_run_id: Mapped[str] = mapped_column(ForeignKey("analytics_runs.id"), nullable=False, index=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), nullable=False, index=True)
    indicator_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    glucose_event_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    avg_glucose: Mapped[float | None] = mapped_column(Float)
    median_glucose: Mapped[float | None] = mapped_column(Float)
    min_glucose: Mapped[float | None] = mapped_column(Float)
    max_glucose: Mapped[float | None] = mapped_column(Float)
    std_glucose: Mapped[float | None] = mapped_column(Float)
    coefficient_of_variation: Mapped[float | None] = mapped_column(Float)
    pct_hypo: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    pct_in_range: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    pct_hyper: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    pre_meal_in_range_pct: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    post_meal_in_range_pct: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    low_events_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    high_events_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    anomaly_score: Mapped[float | None] = mapped_column(Float)
    anomaly_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    cluster_label: Mapped[int | None] = mapped_column(Integer)
    report_json: Mapped[dict | None] = mapped_column(JSON)

    analytics_run: Mapped["AnalyticsRun"] = relationship(back_populates="indicators")
    patient: Mapped["Patient"] = relationship(back_populates="daily_indicators")


class DataQualityIssue(Base):
    __tablename__ = "data_quality_issues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    import_batch_id: Mapped[str] = mapped_column(ForeignKey("import_batches.id"), nullable=False, index=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), nullable=False, index=True)
    raw_event_id: Mapped[int | None] = mapped_column(ForeignKey("raw_events.id"))
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="info")
    issue_type: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    rule_name: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    import_batch: Mapped["ImportBatch"] = relationship(back_populates="quality_issues")
    patient: Mapped["Patient"] = relationship(back_populates="quality_issues")

