"""Clinical core with UUID provenance strategy.

Revision ID: 20260504_0002
Revises: 20260414_0001
Create Date: 2026-05-04 14:30:00
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op
import sqlalchemy as sa


revision = "20260504_0002"
down_revision = "20260414_0001"
branch_labels = None
depends_on = None


LEGACY_TABLES = [
    "data_quality_issues",
    "daily_indicators",
    "analytics_runs",
    "normalized_events",
    "raw_events",
    "patients",
    "import_batches",
]

# Reverse dependency order of the tables created below.
CLINICAL_CORE_TABLES = [
    "glucose_record_sources",
    "data_quality_issues",
    "raw_import_records",
    "patient_source_links",
    "daily_indicators",
    "import_batches",
    "glucose_records",
    "daily_metrics_current",
    "analysis_runs",
    "analysis_outbox",
    "provenance_events",
    "provenance_artifacts",
    "patients",
    "data_sources",
]


def upgrade() -> None:
    # The integer-keyed MVP tables are replaced, not converted: their rows are
    # rebuilt by re-running the UCI import against the UUID clinical core.
    for table_name in LEGACY_TABLES:
        op.drop_table(table_name)

    # Frozen DDL: the clinical core as defined by app/models/entities.py when
    # this revision was written (commit 3093435). Never derive it from the
    # current ORM models; later schema changes belong to later revisions.
    op.create_table(
    "data_sources",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("uri", sa.String(length=500), nullable=True),
        sa.Column("version", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_data_sources_source_type", "data_sources", ["source_type"])

    op.create_table(
    "patients",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_patients_name", "patients", ["name"])

    op.create_table(
    "provenance_artifacts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_type", sa.String(length=80), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("artifact_type", sa.String(length=80), nullable=False),
        sa.Column("format", sa.String(length=40), nullable=False),
        sa.Column("path", sa.String(length=500), nullable=False),
        sa.Column("content_hash", sa.String(length=128), nullable=True),
        sa.Column("hash_algorithm", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_provenance_artifacts_artifact_type", "provenance_artifacts", ["artifact_type"])
    op.create_index("ix_provenance_artifacts_content_hash", "provenance_artifacts", ["content_hash"])
    op.create_index("ix_provenance_artifacts_owner_id", "provenance_artifacts", ["owner_id"])
    op.create_index("ix_provenance_artifacts_owner_type", "provenance_artifacts", ["owner_type"])
    op.create_index("ix_provenance_artifacts_status", "provenance_artifacts", ["status"])

    op.create_table(
    "provenance_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("activity_type", sa.String(length=120), nullable=False),
        sa.Column("entity_type", sa.String(length=120), nullable=False),
        sa.Column("entity_id", sa.String(length=36), nullable=False),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column("source_type", sa.String(length=80), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=True),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("prov_json", sa.JSON(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("content_hash", sa.String(length=128), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_provenance_events_activity_type", "provenance_events", ["activity_type"])
    op.create_index("ix_provenance_events_actor_user_id", "provenance_events", ["actor_user_id"])
    op.create_index("ix_provenance_events_content_hash", "provenance_events", ["content_hash"])
    op.create_index("ix_provenance_events_entity_id", "provenance_events", ["entity_id"])
    op.create_index("ix_provenance_events_entity_type", "provenance_events", ["entity_type"])
    op.create_index("ix_provenance_events_source_id", "provenance_events", ["source_id"])
    op.create_index("ix_provenance_events_source_type", "provenance_events", ["source_type"])

    op.create_table(
    "analysis_outbox",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("patient_id", sa.String(length=36), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("trigger_type", sa.String(length=60), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"]),
    )
    op.create_index("ix_analysis_outbox_end_date", "analysis_outbox", ["end_date"])
    op.create_index("ix_analysis_outbox_patient_id", "analysis_outbox", ["patient_id"])
    op.create_index("ix_analysis_outbox_start_date", "analysis_outbox", ["start_date"])
    op.create_index("ix_analysis_outbox_status", "analysis_outbox", ["status"])

    op.create_table(
    "analysis_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("patient_id", sa.String(length=36), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("trigger_type", sa.String(length=60), nullable=False),
        sa.Column("algorithm_name", sa.String(length=120), nullable=False),
        sa.Column("algorithm_version", sa.String(length=40), nullable=False),
        sa.Column("parameters_json", sa.JSON(), nullable=True),
        sa.Column("environment_json", sa.JSON(), nullable=True),
        sa.Column("code_version", sa.String(length=120), nullable=True),
        sa.Column("input_fingerprint", sa.String(length=128), nullable=True),
        sa.Column("output_fingerprint", sa.String(length=128), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"]),
    )
    op.create_index("ix_analysis_runs_end_date", "analysis_runs", ["end_date"])
    op.create_index("ix_analysis_runs_input_fingerprint", "analysis_runs", ["input_fingerprint"])
    op.create_index("ix_analysis_runs_output_fingerprint", "analysis_runs", ["output_fingerprint"])
    op.create_index("ix_analysis_runs_patient_id", "analysis_runs", ["patient_id"])
    op.create_index("ix_analysis_runs_start_date", "analysis_runs", ["start_date"])
    op.create_index("ix_analysis_runs_status", "analysis_runs", ["status"])

    op.create_table(
    "daily_metrics_current",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("patient_id", sa.String(length=36), nullable=False),
        sa.Column("metric_date", sa.Date(), nullable=False),
        sa.Column("glucose_event_count", sa.Integer(), nullable=False),
        sa.Column("avg_glucose", sa.Float(), nullable=True),
        sa.Column("min_glucose", sa.Float(), nullable=True),
        sa.Column("max_glucose", sa.Float(), nullable=True),
        sa.Column("pct_hypo", sa.Float(), nullable=False),
        sa.Column("pct_in_range", sa.Float(), nullable=False),
        sa.Column("pct_hyper", sa.Float(), nullable=False),
        sa.Column("low_events_count", sa.Integer(), nullable=False),
        sa.Column("high_events_count", sa.Integer(), nullable=False),
        sa.Column("freshness_status", sa.String(length=40), nullable=False),
        sa.Column("input_fingerprint", sa.String(length=128), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("patient_id", "metric_date", name="uq_daily_metrics_patient_day"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"]),
    )
    op.create_index("ix_daily_metrics_current_freshness_status", "daily_metrics_current", ["freshness_status"])
    op.create_index("ix_daily_metrics_current_input_fingerprint", "daily_metrics_current", ["input_fingerprint"])
    op.create_index("ix_daily_metrics_current_metric_date", "daily_metrics_current", ["metric_date"])
    op.create_index("ix_daily_metrics_current_patient_id", "daily_metrics_current", ["patient_id"])

    op.create_table(
    "glucose_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("patient_id", sa.String(length=36), nullable=False),
        sa.Column("measured_at", sa.DateTime(), nullable=False),
        sa.Column("glucose_mg_dl", sa.Float(), nullable=False),
        sa.Column("context_label", sa.String(length=80), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"]),
    )
    op.create_index("ix_glucose_records_context_label", "glucose_records", ["context_label"])
    op.create_index("ix_glucose_records_measured_at", "glucose_records", ["measured_at"])
    op.create_index("ix_glucose_records_patient_id", "glucose_records", ["patient_id"])

    op.create_table(
    "import_batches",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("data_source_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("raw_record_count", sa.Integer(), nullable=False),
        sa.Column("normalized_record_count", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_sources.id"]),
    )
    op.create_index("ix_import_batches_data_source_id", "import_batches", ["data_source_id"])
    op.create_index("ix_import_batches_status", "import_batches", ["status"])

    op.create_table(
    "daily_indicators",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("analysis_run_id", sa.String(length=36), nullable=False),
        sa.Column("patient_id", sa.String(length=36), nullable=False),
        sa.Column("indicator_date", sa.Date(), nullable=False),
        sa.Column("glucose_event_count", sa.Integer(), nullable=False),
        sa.Column("avg_glucose", sa.Float(), nullable=True),
        sa.Column("median_glucose", sa.Float(), nullable=True),
        sa.Column("min_glucose", sa.Float(), nullable=True),
        sa.Column("max_glucose", sa.Float(), nullable=True),
        sa.Column("std_glucose", sa.Float(), nullable=True),
        sa.Column("coefficient_of_variation", sa.Float(), nullable=True),
        sa.Column("pct_hypo", sa.Float(), nullable=False),
        sa.Column("pct_in_range", sa.Float(), nullable=False),
        sa.Column("pct_hyper", sa.Float(), nullable=False),
        sa.Column("pre_meal_in_range_pct", sa.Float(), nullable=False),
        sa.Column("post_meal_in_range_pct", sa.Float(), nullable=False),
        sa.Column("low_events_count", sa.Integer(), nullable=False),
        sa.Column("high_events_count", sa.Integer(), nullable=False),
        sa.Column("anomaly_score", sa.Float(), nullable=True),
        sa.Column("anomaly_flag", sa.Boolean(), nullable=False),
        sa.Column("cluster_label", sa.Integer(), nullable=True),
        sa.Column("report_json", sa.JSON(), nullable=True),
        sa.UniqueConstraint("analysis_run_id", "patient_id", "indicator_date", name="uq_indicator_run_patient_day"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["analysis_run_id"], ["analysis_runs.id"]),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"]),
    )
    op.create_index("ix_daily_indicators_analysis_run_id", "daily_indicators", ["analysis_run_id"])
    op.create_index("ix_daily_indicators_indicator_date", "daily_indicators", ["indicator_date"])
    op.create_index("ix_daily_indicators_patient_id", "daily_indicators", ["patient_id"])

    op.create_table(
    "patient_source_links",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("patient_id", sa.String(length=36), nullable=False),
        sa.Column("data_source_id", sa.String(length=36), nullable=False),
        sa.Column("import_batch_id", sa.String(length=36), nullable=True),
        sa.Column("external_patient_code", sa.String(length=120), nullable=False),
        sa.Column("source_file", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("data_source_id", "external_patient_code", name="uq_patient_source_external_code"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"]),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_sources.id"]),
        sa.ForeignKeyConstraint(["import_batch_id"], ["import_batches.id"]),
    )
    op.create_index("ix_patient_source_links_data_source_id", "patient_source_links", ["data_source_id"])
    op.create_index("ix_patient_source_links_import_batch_id", "patient_source_links", ["import_batch_id"])
    op.create_index("ix_patient_source_links_patient_id", "patient_source_links", ["patient_id"])

    op.create_table(
    "raw_import_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("import_batch_id", sa.String(length=36), nullable=False),
        sa.Column("patient_id", sa.String(length=36), nullable=True),
        sa.Column("source_file", sa.String(length=255), nullable=False),
        sa.Column("source_line", sa.Integer(), nullable=False),
        sa.Column("raw_payload", sa.Text(), nullable=False),
        sa.Column("raw_date", sa.String(length=20), nullable=True),
        sa.Column("raw_time", sa.String(length=10), nullable=True),
        sa.Column("raw_code", sa.String(length=40), nullable=True),
        sa.Column("raw_value", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("import_batch_id", "source_file", "source_line", name="uq_raw_import_batch_file_line"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["import_batch_id"], ["import_batches.id"]),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"]),
    )
    op.create_index("ix_raw_import_records_import_batch_id", "raw_import_records", ["import_batch_id"])
    op.create_index("ix_raw_import_records_patient_id", "raw_import_records", ["patient_id"])

    op.create_table(
    "data_quality_issues",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("import_batch_id", sa.String(length=36), nullable=True),
        sa.Column("raw_import_record_id", sa.String(length=36), nullable=True),
        sa.Column("glucose_record_id", sa.String(length=36), nullable=True),
        sa.Column("patient_id", sa.String(length=36), nullable=True),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("issue_type", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("rule_name", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["import_batch_id"], ["import_batches.id"]),
        sa.ForeignKeyConstraint(["raw_import_record_id"], ["raw_import_records.id"]),
        sa.ForeignKeyConstraint(["glucose_record_id"], ["glucose_records.id"]),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"]),
    )
    op.create_index("ix_data_quality_issues_glucose_record_id", "data_quality_issues", ["glucose_record_id"])
    op.create_index("ix_data_quality_issues_import_batch_id", "data_quality_issues", ["import_batch_id"])
    op.create_index("ix_data_quality_issues_issue_type", "data_quality_issues", ["issue_type"])
    op.create_index("ix_data_quality_issues_patient_id", "data_quality_issues", ["patient_id"])
    op.create_index("ix_data_quality_issues_raw_import_record_id", "data_quality_issues", ["raw_import_record_id"])
    op.create_index("ix_data_quality_issues_source_type", "data_quality_issues", ["source_type"])
    op.create_index("ix_data_quality_issues_status", "data_quality_issues", ["status"])

    op.create_table(
    "glucose_record_sources",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("glucose_record_id", sa.String(length=36), nullable=False),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column("import_batch_id", sa.String(length=36), nullable=True),
        sa.Column("raw_import_record_id", sa.String(length=36), nullable=True),
        sa.Column("device_id", sa.String(length=120), nullable=True),
        sa.Column("entered_at", sa.DateTime(), nullable=False),
        sa.Column("transformation_rule", sa.String(length=160), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["glucose_record_id"], ["glucose_records.id"]),
        sa.ForeignKeyConstraint(["import_batch_id"], ["import_batches.id"]),
        sa.ForeignKeyConstraint(["raw_import_record_id"], ["raw_import_records.id"]),
    )
    op.create_index("ix_glucose_record_sources_actor_user_id", "glucose_record_sources", ["actor_user_id"])
    op.create_index("ix_glucose_record_sources_device_id", "glucose_record_sources", ["device_id"])
    op.create_index("ix_glucose_record_sources_glucose_record_id", "glucose_record_sources", ["glucose_record_id"])
    op.create_index("ix_glucose_record_sources_import_batch_id", "glucose_record_sources", ["import_batch_id"])
    op.create_index("ix_glucose_record_sources_raw_import_record_id", "glucose_record_sources", ["raw_import_record_id"])
    op.create_index("ix_glucose_record_sources_source_type", "glucose_record_sources", ["source_type"])


def downgrade() -> None:
    # Indexes are dropped with their tables; MySQL refuses to drop an index
    # that still backs a foreign key.
    for table_name in CLINICAL_CORE_TABLES:
        op.drop_table(table_name)
    # Restore the (empty) legacy schema so 20260414_0001 stays consistent.
    spec = importlib.util.spec_from_file_location(
        "myglico_migration_20260414_0001", Path(__file__).with_name("20260414_0001_initial.py")
    )
    initial = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(initial)
    initial.upgrade()
