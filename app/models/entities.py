from __future__ import annotations

from datetime import date, datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.crypto import decrypt_field, email_lookup, encrypt_field, generate_short_id
from app.db.base import Base


def _uuid() -> str:
    return str(uuid4())


def _now() -> datetime:
    return datetime.utcnow()


class Patient(Base):
    __tablename__ = "patients"
    __table_args__ = (
        UniqueConstraint("short_id", name="uq_patients_short_id"),
        UniqueConstraint("user_account_id", name="uq_patients_user_account_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    email_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    short_id: Mapped[str] = mapped_column(String(6), nullable=False, default=generate_short_id)
    user_account_id: Mapped[str | None] = mapped_column(ForeignKey("user_accounts.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now, nullable=False)

    user_account: Mapped["UserAccount | None"] = relationship(back_populates="patient")
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
    def name(self) -> str:
        return decrypt_field(self.name_encrypted, table="patients", column="name", record_id=self.id) or ""

    @name.setter
    def name(self, value: str) -> None:
        if self.id is None:
            self.id = _uuid()
        self.name_encrypted = encrypt_field(
            value, table="patients", column="name", record_id=self.id
        )  # type: ignore[assignment]

    @property
    def email(self) -> str | None:
        return decrypt_field(self.email_encrypted, table="patients", column="email", record_id=self.id)

    @email.setter
    def email(self, value: str | None) -> None:
        if self.id is None:
            self.id = _uuid()
        self.email_encrypted = encrypt_field(value, table="patients", column="email", record_id=self.id)

    @property
    def source_file(self) -> str:
        if self.source_links:
            return self.source_links[0].source_file or "manual"
        return "manual"


class UserAccount(Base):
    __tablename__ = "user_accounts"
    __table_args__ = (UniqueConstraint("email_lookup", name="uq_user_accounts_email_lookup"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    email_lookup: Mapped[str] = mapped_column(String(64), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    account_status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    patient: Mapped[Patient | None] = relationship(back_populates="user_account", uselist=False)
    doctor: Mapped["Doctor | None"] = relationship(back_populates="user_account", uselist=False)
    sessions: Mapped[list["UserSession"]] = relationship(back_populates="user_account", cascade="all, delete-orphan")

    @property
    def email(self) -> str:
        return decrypt_field(self.email_encrypted, table="user_accounts", column="email", record_id=self.id) or ""

    @email.setter
    def email(self, value: str) -> None:
        if self.id is None:
            self.id = _uuid()
        self.email_encrypted = encrypt_field(
            value, table="user_accounts", column="email", record_id=self.id
        )  # type: ignore[assignment]
        self.email_lookup = email_lookup(value)


class Doctor(Base):
    __tablename__ = "doctors"
    __table_args__ = (
        UniqueConstraint("short_id", name="uq_doctors_short_id"),
        UniqueConstraint("user_account_id", name="uq_doctors_user_account_id"),
        UniqueConstraint("crm_uf_lookup", name="uq_doctors_crm_uf_lookup"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    short_id: Mapped[str] = mapped_column(String(6), nullable=False, default=generate_short_id)
    user_account_id: Mapped[str] = mapped_column(ForeignKey("user_accounts.id"), nullable=False)
    name_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    crm_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    uf_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    crm_uf_lookup: Mapped[str | None] = mapped_column(String(64))
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    declared_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now, nullable=False)

    user_account: Mapped[UserAccount] = relationship(back_populates="doctor")


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_account_id: Mapped[str] = mapped_column(ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)

    user_account: Mapped[UserAccount] = relationship(back_populates="sessions")


class PatientDoctorLink(Base):
    __tablename__ = "patient_doctor_links"
    # One non-null marker for an open cycle; terminal cycles retain NULL.
    __table_args__ = (
        UniqueConstraint("patient_id", "doctor_id", "open_pair_key", name="uq_patient_doctor_open_cycle"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), nullable=False, index=True)
    doctor_id: Mapped[str] = mapped_column(ForeignKey("doctors.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING", index=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)
    revoked_by_role: Mapped[str | None] = mapped_column(String(16))
    reason_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    open_pair_key: Mapped[str | None] = mapped_column(String(8), nullable=True, default="open")
    patient: Mapped[Patient] = relationship()
    doctor: Mapped[Doctor] = relationship()


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    recipient_user_account_id: Mapped[str] = mapped_column(
        ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    notification_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    causation_event_id: Mapped[str] = mapped_column(
        ForeignKey("provenance_events.id"), nullable=False, index=True
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)


class NotificationOutbox(Base):
    __tablename__ = "notification_outbox"
    __table_args__ = (UniqueConstraint("notification_id", name="uq_notification_outbox_notification"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    notification_id: Mapped[str] = mapped_column(ForeignKey("notifications.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING", index=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime)


class Investigation(Base):
    __tablename__ = "investigations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), nullable=False, index=True)
    doctor_id: Mapped[str] = mapped_column(ForeignKey("doctors.id"), nullable=False, index=True)
    association_id: Mapped[str] = mapped_column(ForeignKey("patient_doctor_links.id"), nullable=False, index=True)
    atypical_day_event_id: Mapped[str | None] = mapped_column(ForeignKey("daily_indicators.id"), index=True)
    title_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="OPEN", index=True)
    awaiting_role: Mapped[str | None] = mapped_column(String(16))
    opened_by_role: Mapped[str] = mapped_column(String(16), nullable=False)
    opened_by_domain_id: Mapped[str] = mapped_column(String(36), nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)
    closed_by: Mapped[str | None] = mapped_column(String(36))
    closed_reason: Mapped[str | None] = mapped_column(String(80))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class InvestigationMessage(Base):
    __tablename__ = "investigation_messages"
    __table_args__ = (
        UniqueConstraint("investigation_id", "sequence", name="uq_investigation_message_sequence"),
        UniqueConstraint("investigation_id", "idempotency_key", name="uq_investigation_message_idempotency"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False, index=True)
    author_role: Mapped[str] = mapped_column(String(16), nullable=False)
    author_domain_id: Mapped[str] = mapped_column(String(36), nullable=False)
    content_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(128))


class InvestigationReadPosition(Base):
    __tablename__ = "investigation_read_positions"

    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigations.id", ondelete="CASCADE"), primary_key=True)
    participant_role: Mapped[str] = mapped_column(String(16), primary_key=True)
    participant_domain_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    last_read_sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now, nullable=False)


class AtypicalDayPrompt(Base):
    __tablename__ = "atypical_day_prompts"
    __table_args__ = (
        UniqueConstraint("patient_id", "indicator_date", name="uq_atypical_prompt_patient_date"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), nullable=False, index=True)
    daily_indicator_id: Mapped[str] = mapped_column(ForeignKey("daily_indicators.id"), nullable=False, index=True)
    indicator_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="CREATED", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)

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
    notes_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now, nullable=False)

    patient: Mapped["Patient"] = relationship(back_populates="glucose_records")
    sources: Mapped[list["GlucoseRecordSource"]] = relationship(back_populates="glucose_record", cascade="all, delete-orphan")
    quality_issues: Mapped[list["DataQualityIssue"]] = relationship(back_populates="glucose_record")

    @property
    def notes(self) -> str | None:
        return decrypt_field(
            self.notes_encrypted, table="glucose_records", column="notes", record_id=self.id,
        )

    @notes.setter
    def notes(self, value: str | None) -> None:
        if value is not None and not getattr(self, "id", None):
            self.id = _uuid()
        self.notes_encrypted = encrypt_field(
            value, table="glucose_records", column="notes", record_id=self.id or "",
        )


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
