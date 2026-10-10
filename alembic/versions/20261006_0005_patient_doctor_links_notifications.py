"""Persist patient-doctor association cycles and internal notifications.

Revision ID: 20261006_0005
Revises: 20261006_0004
Create Date: 2026-10-06
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20261006_0005"
down_revision = "20261006_0004"
branch_labels = None
depends_on = None


# Frozen DDL: never derive this revision's schema from the current ORM models.
def upgrade() -> None:
    op.create_table(
        "patient_doctor_links",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("patient_id", sa.String(length=36), nullable=False),
        sa.Column("doctor_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("requested_at", sa.DateTime(), nullable=False),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_by_role", sa.String(length=16), nullable=True),
        sa.Column("reason_encrypted", sa.LargeBinary(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        # One non-null marker for an open cycle; terminal cycles retain NULL.
        sa.Column("open_pair_key", sa.String(length=8), nullable=True),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"]),
        sa.ForeignKeyConstraint(["doctor_id"], ["doctors.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("patient_id", "doctor_id", "open_pair_key", name="uq_patient_doctor_open_cycle"),
    )
    op.create_index("ix_patient_doctor_links_doctor_id", "patient_doctor_links", ["doctor_id"])
    op.create_index("ix_patient_doctor_links_patient_id", "patient_doctor_links", ["patient_id"])
    op.create_index("ix_patient_doctor_links_status", "patient_doctor_links", ["status"])

    op.create_table(
        "notifications",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("recipient_user_account_id", sa.String(length=36), nullable=False),
        sa.Column("notification_type", sa.String(length=80), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("causation_event_id", sa.String(length=36), nullable=False),
        sa.Column("read_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["recipient_user_account_id"], ["user_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["causation_event_id"], ["provenance_events.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notifications_causation_event_id", "notifications", ["causation_event_id"])
    op.create_index("ix_notifications_notification_type", "notifications", ["notification_type"])
    op.create_index("ix_notifications_read_at", "notifications", ["read_at"])
    op.create_index("ix_notifications_recipient_user_account_id", "notifications", ["recipient_user_account_id"])


def downgrade() -> None:
    # Indexes are dropped with their tables; MySQL refuses to drop an index
    # that still backs a foreign key.
    op.drop_table("notifications")
    op.drop_table("patient_doctor_links")
