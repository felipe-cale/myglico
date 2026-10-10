"""Persist CSCW investigations, messages, read positions, and atypical prompts.

Revision ID: 20261006_0006
Revises: 20261006_0005
Create Date: 2026-10-06
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20261006_0006"
down_revision = "20261006_0005"
branch_labels = None
depends_on = None


# Frozen DDL: never derive this revision's schema from the current ORM models.
# notification_outbox.next_attempt_at/last_error and the wider
# investigations.closed_by belong to revision 20261007_0008.
def upgrade() -> None:
    op.create_table(
        "notification_outbox",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("notification_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["notification_id"], ["notifications.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("notification_id", name="uq_notification_outbox_notification"),
    )
    op.create_index("ix_notification_outbox_status", "notification_outbox", ["status"])

    op.create_table(
        "investigations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("patient_id", sa.String(length=36), nullable=False),
        sa.Column("doctor_id", sa.String(length=36), nullable=False),
        sa.Column("association_id", sa.String(length=36), nullable=False),
        sa.Column("atypical_day_event_id", sa.String(length=36), nullable=True),
        sa.Column("title_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("awaiting_role", sa.String(length=16), nullable=True),
        sa.Column("opened_by_role", sa.String(length=16), nullable=False),
        sa.Column("opened_by_domain_id", sa.String(length=36), nullable=False),
        sa.Column("opened_at", sa.DateTime(), nullable=False),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
        sa.Column("closed_by", sa.String(length=36), nullable=True),
        sa.Column("closed_reason", sa.String(length=80), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"]),
        sa.ForeignKeyConstraint(["doctor_id"], ["doctors.id"]),
        sa.ForeignKeyConstraint(["association_id"], ["patient_doctor_links.id"]),
        sa.ForeignKeyConstraint(["atypical_day_event_id"], ["daily_indicators.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_investigations_association_id", "investigations", ["association_id"])
    op.create_index("ix_investigations_atypical_day_event_id", "investigations", ["atypical_day_event_id"])
    op.create_index("ix_investigations_doctor_id", "investigations", ["doctor_id"])
    op.create_index("ix_investigations_patient_id", "investigations", ["patient_id"])
    op.create_index("ix_investigations_status", "investigations", ["status"])

    op.create_table(
        "investigation_messages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("investigation_id", sa.String(length=36), nullable=False),
        sa.Column("author_role", sa.String(length=16), nullable=False),
        sa.Column("author_domain_id", sa.String(length=36), nullable=False),
        sa.Column("content_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.ForeignKeyConstraint(["investigation_id"], ["investigations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("investigation_id", "sequence", name="uq_investigation_message_sequence"),
        sa.UniqueConstraint("investigation_id", "idempotency_key", name="uq_investigation_message_idempotency"),
    )
    op.create_index("ix_investigation_messages_investigation_id", "investigation_messages", ["investigation_id"])

    op.create_table(
        "investigation_read_positions",
        sa.Column("investigation_id", sa.String(length=36), nullable=False),
        sa.Column("participant_role", sa.String(length=16), nullable=False),
        sa.Column("participant_domain_id", sa.String(length=36), nullable=False),
        sa.Column("last_read_sequence", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["investigation_id"], ["investigations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("investigation_id", "participant_role", "participant_domain_id"),
    )

    op.create_table(
        "atypical_day_prompts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("patient_id", sa.String(length=36), nullable=False),
        sa.Column("daily_indicator_id", sa.String(length=36), nullable=False),
        sa.Column("indicator_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"]),
        sa.ForeignKeyConstraint(["daily_indicator_id"], ["daily_indicators.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("patient_id", "indicator_date", name="uq_atypical_prompt_patient_date"),
    )
    op.create_index("ix_atypical_day_prompts_daily_indicator_id", "atypical_day_prompts", ["daily_indicator_id"])
    op.create_index("ix_atypical_day_prompts_patient_id", "atypical_day_prompts", ["patient_id"])
    op.create_index("ix_atypical_day_prompts_status", "atypical_day_prompts", ["status"])


def downgrade() -> None:
    # Indexes are dropped with their tables; MySQL refuses to drop an index
    # that still backs a foreign key.
    op.drop_table("atypical_day_prompts")
    op.drop_table("investigation_read_positions")
    op.drop_table("investigation_messages")
    op.drop_table("investigations")
    op.drop_table("notification_outbox")
