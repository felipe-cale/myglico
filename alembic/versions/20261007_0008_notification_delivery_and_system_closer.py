"""Track notification delivery retries and system association closures.

Revision ID: 20261007_0008
Revises: 20261007_0007
Create Date: 2026-10-07
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20261007_0008"
down_revision = "20261007_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    outbox_columns = {column["name"] for column in inspector.get_columns("notification_outbox")}
    if "next_attempt_at" not in outbox_columns:
        op.add_column("notification_outbox", sa.Column("next_attempt_at", sa.DateTime(), nullable=True))
    if "last_error" not in outbox_columns:
        op.add_column("notification_outbox", sa.Column("last_error", sa.String(length=120), nullable=True))
    outbox_indexes = {index["name"] for index in inspector.get_indexes("notification_outbox")}
    if "ix_notification_outbox_next_attempt_at" not in outbox_indexes:
        op.create_index("ix_notification_outbox_next_attempt_at", "notification_outbox", ["next_attempt_at"])

    investigation_columns = {column["name"]: column for column in inspector.get_columns("investigations")}
    closed_by_type = investigation_columns["closed_by"]["type"]
    if getattr(closed_by_type, "length", None) != 80:
        with op.batch_alter_table("investigations") as batch_op:
            batch_op.alter_column(
                "closed_by", existing_type=closed_by_type, type_=sa.String(length=80),
                existing_nullable=True,
            )


def downgrade() -> None:
    with op.batch_alter_table("investigations") as batch_op:
        batch_op.alter_column(
            "closed_by", existing_type=sa.String(length=80), type_=sa.String(length=36),
            existing_nullable=True,
        )
    op.drop_index("ix_notification_outbox_next_attempt_at", table_name="notification_outbox")
    op.drop_column("notification_outbox", "last_error")
    op.drop_column("notification_outbox", "next_attempt_at")
