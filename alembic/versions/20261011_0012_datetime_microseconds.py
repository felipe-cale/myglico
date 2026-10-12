"""Preserve microseconds in MySQL timestamps.

Revision ID: 20261011_0012
Revises: 20261008_0011
Create Date: 2026-10-11
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import DATETIME as MySQLDateTime


revision = "20261011_0012"
down_revision = "20261008_0011"
branch_labels = None
depends_on = None


# Frozen DDL: all timestamps in the current schema, with nullability recorded
# as it exists at this revision. SQLite stores fractional seconds regardless of
# the declared precision; MySQL needs DATETIME(6) to avoid truncating them.
_DATETIME_COLUMNS = (
    ("data_sources", "created_at", False),
    ("provenance_artifacts", "created_at", False),
    ("provenance_events", "occurred_at", False),
    ("user_accounts", "email_verified_at", True),
    ("user_accounts", "created_at", False),
    ("user_accounts", "updated_at", False),
    ("user_accounts", "privacy_notice_accepted_at", True),
    ("doctors", "created_at", False),
    ("doctors", "updated_at", False),
    ("import_batches", "started_at", False),
    ("import_batches", "finished_at", True),
    ("notifications", "read_at", True),
    ("notifications", "created_at", False),
    ("patients", "created_at", False),
    ("patients", "updated_at", False),
    ("user_sessions", "created_at", False),
    ("user_sessions", "expires_at", False),
    ("user_sessions", "revoked_at", True),
    ("analysis_outbox", "created_at", False),
    ("analysis_outbox", "processed_at", True),
    ("analysis_runs", "started_at", False),
    ("analysis_runs", "finished_at", True),
    ("analysis_runs", "created_at", False),
    ("daily_metrics_current", "updated_at", False),
    ("glucose_records", "measured_at", False),
    ("glucose_records", "created_at", False),
    ("glucose_records", "updated_at", False),
    ("notification_outbox", "next_attempt_at", True),
    ("notification_outbox", "created_at", False),
    ("notification_outbox", "processed_at", True),
    ("patient_doctor_links", "requested_at", False),
    ("patient_doctor_links", "decided_at", True),
    ("patient_doctor_links", "revoked_at", True),
    ("patient_source_links", "created_at", False),
    ("raw_import_records", "created_at", False),
    ("data_quality_issues", "created_at", False),
    ("glucose_record_sources", "entered_at", False),
    ("atypical_day_prompts", "created_at", False),
    ("investigations", "opened_at", False),
    ("investigations", "closed_at", True),
    ("investigation_messages", "created_at", False),
    ("investigation_read_positions", "updated_at", False),
)


def _set_precision(precision: int) -> None:
    connection = op.get_bind()
    if connection.dialect.name != "mysql":
        return
    for table_name, column_name, nullable in _DATETIME_COLUMNS:
        op.alter_column(
            table_name,
            column_name,
            existing_type=sa.DateTime(),
            type_=MySQLDateTime(fsp=precision),
            existing_nullable=nullable,
        )


def upgrade() -> None:
    _set_precision(6)


def downgrade() -> None:
    _set_precision(0)
