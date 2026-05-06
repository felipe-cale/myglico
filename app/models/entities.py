from __future__ import annotations

from datetime import date, datetime
from uuid import uuid4

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _uuid() -> str:
    return str(uuid4())


def _now() -> datetime:
    return datetime.utcnow()


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    email: Mapped[str | None] = mapped_column(String(254), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now, nullable=False)

    glucose_records: Mapped[list["GlucoseRecord"]] = relationship(back_populates="patient")
    source_links: Mapped[list["PatientSourceLink"]] = relationship(back_populates="patient", cascade="all, delete-orphan")
    daily_metrics: Mapped[list["DailyMetricsCurrent"]] = relationship(back_populates="patient", cascade="all, delete-orphan")
    analysis_runs: Mapped[list["AnalysisRun"]] = relationship(back_populates="patient")
    daily_indicators: Mapped[list["DailyIndicator"]] = relationship(back_populates="patient")
    quality_issues: Mapped[list["DataQualityIssue"]] = relationship(back_populates="patient")

    @property
    def display_name(self) -> str:
        return self.name

    @property
    def source_file(self) -> str:
        if self.source_links:
            return self.source_links[0].source_file or "manual"
        return "manual"


class DataSource(Base):
    __tablename__ = "data_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    uri: Mapped[str | None] = mapped_column(String(500))
    version: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)

    import_batches: Mapped[list["ImportBatch"]] = relationship(back_populates="data_source", cascade="all, delete-orphan")
    patient_links: Mapped[list["PatientSourceLink"]] = relationship(back_populates="data_source")


class ImportBatch(Base):
    __tablename__ = "import_batches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    data_source_id: Mapped[str] = mapped_column(ForeignKey("data_sources.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), default="running", nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    raw_record_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    normalized_record_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    data_source: Mapped["DataSource"] = relationship(back_populates="import_batches")
    patient_links: Mapped[list["PatientSourceLink"]] = relationship(back_populates="import_batch")
    raw_import_records: Mapped[list["RawImportRecord"]] = relationship(back_populates="import_batch", cascade="all, delete-orphan")
    record_sources: Mapped[list["GlucoseRecordSource"]] = relationship(back_populates="import_batch")
    quality_issues: Mapped[list["DataQualityIssue"]] = relationship(back_populates="import_batch")


class PatientSourceLink(Base):
    __tablename__ = "patient_source_links"
    __table_args__ = (UniqueConstraint("data_source_id", "external_patient_code", name="uq_patient_source_external_code"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), nullable=False, index=True)
    data_source_id: Mapped[str] = mapped_column(ForeignKey("data_sources.id"), nullable=False, index=True)
    import_batch_id: Mapped[str | None] = mapped_column(ForeignKey("import_batches.id"), index=True)
    external_patient_code: Mapped[str] = mapped_column(String(120), nullable=False)
    source_file: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)

    patient: Mapped["Patient"] = relationship(back_populates="source_links")
    data_source: Mapped["DataSource"] = relationship(back_populates="patient_links")
    import_batch: Mapped["ImportBatch"] = relationship(back_populates="patient_links")


class RawImportRecord(Base):
    __tablename__ = "raw_import_records"
    __table_args__ = (UniqueConstraint("import_batch_id", "source_file", "source_line", name="uq_raw_import_batch_file_line"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    import_batch_id: Mapped[str] = mapped_column(ForeignKey("import_batches.id"), nullable=False, index=True)
    patient_id: Mapped[str | None] = mapped_column(ForeignKey("patients.id"), index=True)
    source_file: Mapped[str] = mapped_column(String(255), nullable=False)
    source_line: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_payload: Mapped[str] = mapped_column(Text, nullable=False)
    raw_date: Mapped[str | None] = mapped_column(String(20))
    raw_time: Mapped[str | None] = mapped_column(String(10))
    raw_code: Mapped[str | None] = mapped_column(String(40))
    raw_value: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)

    import_batch: Mapped["ImportBatch"] = relationship(back_populates="raw_import_records")
    patient: Mapped["Patient"] = relationship()
    glucose_sources: Mapped[list["GlucoseRecordSource"]] = relationship(back_populates="raw_import_record")
    quality_issues: Mapped[list["DataQualityIssue"]] = relationship(back_populates="raw_import_record")


class GlucoseRecord(Base):
    __tablename__ = "glucose_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), nullable=False, index=True)
    measured_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    glucose_mg_dl: Mapped[float] = mapped_column(Float, nullable=False)
    context_label: Mapped[str | None] = mapped_column(String(80), index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now, nullable=False)

    patient: Mapped["Patient"] = relationship(back_populates="glucose_records")
    sources: Mapped[list["GlucoseRecordSource"]] = relationship(back_populates="glucose_record", cascade="all, delete-orphan")
    quality_issues: Mapped[list["DataQualityIssue"]] = relationship(back_populates="glucose_record")


class GlucoseRecordSource(Base):
    __tablename__ = "glucose_record_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    glucose_record_id: Mapped[str] = mapped_column(ForeignKey("glucose_records.id"), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    actor_user_id: Mapped[str | None] = mapped_column(String(36), index=True)
    import_batch_id: Mapped[str | None] = mapped_column(ForeignKey("import_batches.id"), index=True)
    raw_import_record_id: Mapped[str | None] = mapped_column(ForeignKey("raw_import_records.id"), index=True)
    device_id: Mapped[str | None] = mapped_column(String(120), index=True)
    entered_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    transformation_rule: Mapped[str | None] = mapped_column(String(160))
    metadata_json: Mapped[dict | None] = mapped_column(JSON)

    glucose_record: Mapped["GlucoseRecord"] = relationship(back_populates="sources")
    import_batch: Mapped["ImportBatch"] = relationship(back_populates="record_sources")
    raw_import_record: Mapped["RawImportRecord"] = relationship(back_populates="glucose_sources")


class DataQualityIssue(Base):
    __tablename__ = "data_quality_issues"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    import_batch_id: Mapped[str | None] = mapped_column(ForeignKey("import_batches.id"), index=True)
    raw_import_record_id: Mapped[str | None] = mapped_column(ForeignKey("raw_import_records.id"), index=True)
    glucose_record_id: Mapped[str | None] = mapped_column(ForeignKey("glucose_records.id"), index=True)
    patient_id: Mapped[str | None] = mapped_column(ForeignKey("patients.id"), index=True)
    severity: Mapped[str] = mapped_column(String(20), default="info", nullable=False)
    issue_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    rule_name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="open", nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)

    import_batch: Mapped["ImportBatch"] = relationship(back_populates="quality_issues")
    raw_import_record: Mapped["RawImportRecord"] = relationship(back_populates="quality_issues")
    glucose_record: Mapped["GlucoseRecord"] = relationship(back_populates="quality_issues")
    patient: Mapped["Patient"] = relationship(back_populates="quality_issues")


class ProvenanceEvent(Base):
    __tablename__ = "provenance_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    activity_type: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    actor_user_id: Mapped[str | None] = mapped_column(String(36), index=True)
    source_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    source_id: Mapped[str | None] = mapped_column(String(36), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    prov_json: Mapped[dict | None] = mapped_column(JSON)
    metadata_json: Mapped[dict | None] = mapped_column(JSON)
    content_hash: Mapped[str | None] = mapped_column(String(128), index=True)


class ProvenanceArtifact(Base):
    __tablename__ = "provenance_artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    owner_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    owner_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    artifact_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    format: Mapped[str] = mapped_column(String(40), nullable=False)
    path: Mapped[str] = mapped_column(String(500), nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(128), index=True)
    hash_algorithm: Mapped[str] = mapped_column(String(20), default="sha256", nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="completed", nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)


class DailyMetricsCurrent(Base):
    __tablename__ = "daily_metrics_current"
    __table_args__ = (UniqueConstraint("patient_id", "metric_date", name="uq_daily_metrics_patient_day"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), nullable=False, index=True)
    metric_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    glucose_event_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    avg_glucose: Mapped[float | None] = mapped_column(Float)
    min_glucose: Mapped[float | None] = mapped_column(Float)
    max_glucose: Mapped[float | None] = mapped_column(Float)
    pct_hypo: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    pct_in_range: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    pct_hyper: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    low_events_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    high_events_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    freshness_status: Mapped[str] = mapped_column(String(40), default="fresh", nullable=False, index=True)
    input_fingerprint: Mapped[str | None] = mapped_column(String(128), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now, nullable=False)

    patient: Mapped["Patient"] = relationship(back_populates="daily_metrics")


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    patient_id: Mapped[str | None] = mapped_column(ForeignKey("patients.id"), index=True)
    start_date: Mapped[date | None] = mapped_column(Date, index=True)
    end_date: Mapped[date | None] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="completed", index=True)
    trigger_type: Mapped[str] = mapped_column(String(60), nullable=False, default="script")
    algorithm_name: Mapped[str] = mapped_column(String(120), nullable=False, default="daily_glycemic_summary")
    algorithm_version: Mapped[str] = mapped_column(String(40), nullable=False, default="v1")
    parameters_json: Mapped[dict | None] = mapped_column(JSON)
    environment_json: Mapped[dict | None] = mapped_column(JSON)
    code_version: Mapped[str | None] = mapped_column(String(120))
    input_fingerprint: Mapped[str | None] = mapped_column(String(128), index=True)
    output_fingerprint: Mapped[str | None] = mapped_column(String(128), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)

    patient: Mapped["Patient"] = relationship(back_populates="analysis_runs")
    indicators: Mapped[list["DailyIndicator"]] = relationship(back_populates="analysis_run", cascade="all, delete-orphan")


class DailyIndicator(Base):
    __tablename__ = "daily_indicators"
    __table_args__ = (UniqueConstraint("analysis_run_id", "patient_id", "indicator_date", name="uq_indicator_run_patient_day"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    analysis_run_id: Mapped[str] = mapped_column(ForeignKey("analysis_runs.id"), nullable=False, index=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), nullable=False, index=True)
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

    analysis_run: Mapped["AnalysisRun"] = relationship(back_populates="indicators")
    patient: Mapped["Patient"] = relationship(back_populates="daily_indicators")


class AnalysisOutbox(Base):
    __tablename__ = "analysis_outbox"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), nullable=False, index=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    end_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    trigger_type: Mapped[str] = mapped_column(String(60), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="pending", nullable=False, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime)
