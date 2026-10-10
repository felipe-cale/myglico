"""Persist revocable server-side authentication sessions.

Revision ID: 20261006_0004
Revises: 20261006_0003
Create Date: 2026-10-06
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20261006_0004"
down_revision = "20261006_0003"
branch_labels = None
depends_on = None


# Frozen DDL: never derive this revision's schema from the current ORM models.
def upgrade() -> None:
    op.create_table(
        "user_sessions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_account_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_account_id"], ["user_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_sessions_expires_at", "user_sessions", ["expires_at"])
    op.create_index("ix_user_sessions_revoked_at", "user_sessions", ["revoked_at"])
    op.create_index("ix_user_sessions_user_account_id", "user_sessions", ["user_account_id"])


def downgrade() -> None:
    # Indexes are dropped with their tables; MySQL refuses to drop an index
    # that still backs a foreign key.
    op.drop_table("user_sessions")
