"""Allow investigations to reference multiple atypical days.

Revision ID: 20261012_0013
Revises: 20261011_0012
Create Date: 2026-10-12
"""

from alembic import op
import sqlalchemy as sa


revision = "20261012_0013"
down_revision = "20261011_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "investigation_atypical_days",
        sa.Column("investigation_id", sa.String(length=36), nullable=False),
        sa.Column("daily_indicator_id", sa.String(length=36), nullable=False),
        sa.Column("indicator_date", sa.Date(), nullable=False),
        sa.ForeignKeyConstraint(["investigation_id"], ["investigations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["daily_indicator_id"], ["daily_indicators.id"]),
        sa.PrimaryKeyConstraint("investigation_id", "daily_indicator_id"),
    )
    op.create_index("ix_investigation_atypical_days_indicator_date", "investigation_atypical_days", ["indicator_date"])
    op.execute(sa.text(
        "INSERT INTO investigation_atypical_days (investigation_id, daily_indicator_id, indicator_date) "
        "SELECT investigations.id, daily_indicators.id, daily_indicators.indicator_date "
        "FROM investigations JOIN daily_indicators ON daily_indicators.id = investigations.atypical_day_event_id "
        "WHERE investigations.atypical_day_event_id IS NOT NULL"
    ))


def downgrade() -> None:
    op.drop_index("ix_investigation_atypical_days_indicator_date", table_name="investigation_atypical_days")
    op.drop_table("investigation_atypical_days")
