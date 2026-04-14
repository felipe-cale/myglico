"""Initial MyGlico MVP schema.

Revision ID: 20260414_0001
Revises:
Create Date: 2026-04-14 11:23:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260414_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "import_batches",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("source_name", sa.String(length=120), nullable=False),
        sa.Column("source_url", sa.String(length=500), nullable=False),
        sa.Column("source_version", sa.String(length=120)),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("imported_at", sa.DateTime(), nullable=False),
        sa.Column("raw_record_count", sa.Integer(), nullable=False),
        sa.Column("normalized_record_count", sa.Integer(), nullable=False),
        sa.Column("provenance_json_path", sa.String(length=500)),
        sa.Column("provenance_ttl_path", sa.String(length=500)),
        sa.Column("notes", sa.Text()),
    )

    op.create_table(
        "patients",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source_patient_code", sa.String(length=40), nullable=False, unique=True),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("source_file", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("notes", sa.Text()),
    )

    op.create_table(
        "raw_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("import_batch_id", sa.String(length=36), sa.ForeignKey("import_batches.id"), nullable=False),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("source_file", sa.String(length=120), nullable=False),
        sa.Column("source_line", sa.Integer(), nullable=False),
        sa.Column("raw_date", sa.String(length=20), nullable=False),
        sa.Column("raw_time", sa.String(length=10), nullable=False),
        sa.Column("raw_code", sa.Integer(), nullable=False),
        sa.Column("raw_value", sa.String(length=40), nullable=False),
        sa.Column("raw_payload", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("patient_id", "source_line", name="uq_raw_event_patient_line"),
    )
    op.create_index("ix_raw_events_import_batch_id", "raw_events", ["import_batch_id"])
    op.create_index("ix_raw_events_patient_id", "raw_events", ["patient_id"])

    op.create_table(
        "normalized_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("import_batch_id", sa.String(length=36), sa.ForeignKey("import_batches.id"), nullable=False),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("raw_event_id", sa.Integer(), sa.ForeignKey("raw_events.id"), nullable=False, unique=True),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("event_time", sa.Time(), nullable=False),
        sa.Column("event_type", sa.String(length=60), nullable=False),
        sa.Column("event_subtype", sa.String(length=80)),
        sa.Column("numeric_value", sa.Float()),
        sa.Column("glucose_mg_dl", sa.Float()),
        sa.Column("insulin_units", sa.Float()),
        sa.Column("context_label", sa.String(length=80)),
        sa.Column("meal_size", sa.String(length=40)),
        sa.Column("exercise_level", sa.String(length=40)),
        sa.Column("symptom_label", sa.String(length=120)),
        sa.Column("special_event_label", sa.String(length=120)),
        sa.Column("is_glucose", sa.Boolean(), nullable=False),
        sa.Column("matches_slot_time", sa.Boolean(), nullable=False),
        sa.Column("timestamp_quality", sa.String(length=40), nullable=False),
        sa.Column("quality_note", sa.Text()),
        sa.Column("provenance_artifact", sa.String(length=500)),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_normalized_events_import_batch_id", "normalized_events", ["import_batch_id"])
    op.create_index("ix_normalized_events_patient_id", "normalized_events", ["patient_id"])
    op.create_index("ix_normalized_events_occurred_at", "normalized_events", ["occurred_at"])
    op.create_index("ix_normalized_events_event_date", "normalized_events", ["event_date"])
    op.create_index("ix_normalized_events_event_type", "normalized_events", ["event_type"])
    op.create_index("ix_normalized_events_context_label", "normalized_events", ["context_label"])

    op.create_table(
        "analytics_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("import_batch_id", sa.String(length=36), sa.ForeignKey("import_batches.id"), nullable=False),
        sa.Column("version", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime()),
        sa.Column("config_json", sa.JSON()),
        sa.Column("provenance_json_path", sa.String(length=500)),
        sa.Column("provenance_ttl_path", sa.String(length=500)),
        sa.Column("semantic_ttl_path", sa.String(length=500)),
    )
    op.create_index("ix_analytics_runs_import_batch_id", "analytics_runs", ["import_batch_id"])

    op.create_table(
        "daily_indicators",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("analytics_run_id", sa.String(length=36), sa.ForeignKey("analytics_runs.id"), nullable=False),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("indicator_date", sa.Date(), nullable=False),
        sa.Column("glucose_event_count", sa.Integer(), nullable=False),
        sa.Column("avg_glucose", sa.Float()),
        sa.Column("median_glucose", sa.Float()),
        sa.Column("min_glucose", sa.Float()),
        sa.Column("max_glucose", sa.Float()),
        sa.Column("std_glucose", sa.Float()),
        sa.Column("coefficient_of_variation", sa.Float()),
        sa.Column("pct_hypo", sa.Float(), nullable=False),
        sa.Column("pct_in_range", sa.Float(), nullable=False),
        sa.Column("pct_hyper", sa.Float(), nullable=False),
        sa.Column("pre_meal_in_range_pct", sa.Float(), nullable=False),
        sa.Column("post_meal_in_range_pct", sa.Float(), nullable=False),
        sa.Column("low_events_count", sa.Integer(), nullable=False),
        sa.Column("high_events_count", sa.Integer(), nullable=False),
        sa.Column("anomaly_score", sa.Float()),
        sa.Column("anomaly_flag", sa.Boolean(), nullable=False),
        sa.Column("cluster_label", sa.Integer()),
        sa.Column("report_json", sa.JSON()),
        sa.UniqueConstraint("analytics_run_id", "patient_id", "indicator_date", name="uq_indicator_day"),
    )
    op.create_index("ix_daily_indicators_analytics_run_id", "daily_indicators", ["analytics_run_id"])
    op.create_index("ix_daily_indicators_patient_id", "daily_indicators", ["patient_id"])
    op.create_index("ix_daily_indicators_indicator_date", "daily_indicators", ["indicator_date"])

    op.create_table(
        "data_quality_issues",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("import_batch_id", sa.String(length=36), sa.ForeignKey("import_batches.id"), nullable=False),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("raw_event_id", sa.Integer(), sa.ForeignKey("raw_events.id")),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("issue_type", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("rule_name", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_data_quality_issues_import_batch_id", "data_quality_issues", ["import_batch_id"])
    op.create_index("ix_data_quality_issues_patient_id", "data_quality_issues", ["patient_id"])


def downgrade() -> None:
    op.drop_index("ix_data_quality_issues_patient_id", table_name="data_quality_issues")
    op.drop_index("ix_data_quality_issues_import_batch_id", table_name="data_quality_issues")
    op.drop_table("data_quality_issues")

    op.drop_index("ix_daily_indicators_indicator_date", table_name="daily_indicators")
    op.drop_index("ix_daily_indicators_patient_id", table_name="daily_indicators")
    op.drop_index("ix_daily_indicators_analytics_run_id", table_name="daily_indicators")
    op.drop_table("daily_indicators")

    op.drop_index("ix_analytics_runs_import_batch_id", table_name="analytics_runs")
    op.drop_table("analytics_runs")

    op.drop_index("ix_normalized_events_context_label", table_name="normalized_events")
    op.drop_index("ix_normalized_events_event_type", table_name="normalized_events")
    op.drop_index("ix_normalized_events_event_date", table_name="normalized_events")
    op.drop_index("ix_normalized_events_occurred_at", table_name="normalized_events")
    op.drop_index("ix_normalized_events_patient_id", table_name="normalized_events")
    op.drop_index("ix_normalized_events_import_batch_id", table_name="normalized_events")
    op.drop_table("normalized_events")

    op.drop_index("ix_raw_events_patient_id", table_name="raw_events")
    op.drop_index("ix_raw_events_import_batch_id", table_name="raw_events")
    op.drop_table("raw_events")

    op.drop_table("patients")
    op.drop_table("import_batches")

