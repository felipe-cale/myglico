"""Clinical core with UUID provenance strategy.

Revision ID: 20260504_0002
Revises: 20260414_0001
Create Date: 2026-05-04 14:30:00
"""

from __future__ import annotations

from alembic import op

from app.db.base import Base
from app.models import entities  # noqa: F401


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


def upgrade() -> None:
    bind = op.get_bind()
    for table_name in LEGACY_TABLES:
        op.drop_table(table_name)

    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
