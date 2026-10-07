"""Persist revocable server-side authentication sessions.

Revision ID: 20261006_0004
Revises: 20261006_0003
Create Date: 2026-10-06
"""

from __future__ import annotations

from alembic import op

from app.models.entities import UserSession


revision = "20261006_0004"
down_revision = "20261006_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    UserSession.__table__.create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    UserSession.__table__.drop(op.get_bind(), checkfirst=True)
