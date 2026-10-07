"""Persist CSCW investigations, messages, read positions, and atypical prompts.

Revision ID: 20261006_0006
Revises: 20261006_0005
Create Date: 2026-10-06
"""

from __future__ import annotations

from alembic import op

from app.models.entities import AtypicalDayPrompt, Investigation, InvestigationMessage, InvestigationReadPosition, NotificationOutbox


revision = "20261006_0006"
down_revision = "20261006_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    NotificationOutbox.__table__.create(op.get_bind(), checkfirst=True)
    Investigation.__table__.create(op.get_bind(), checkfirst=True)
    InvestigationMessage.__table__.create(op.get_bind(), checkfirst=True)
    InvestigationReadPosition.__table__.create(op.get_bind(), checkfirst=True)
    AtypicalDayPrompt.__table__.create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    AtypicalDayPrompt.__table__.drop(op.get_bind(), checkfirst=True)
    InvestigationReadPosition.__table__.drop(op.get_bind(), checkfirst=True)
    InvestigationMessage.__table__.drop(op.get_bind(), checkfirst=True)
    Investigation.__table__.drop(op.get_bind(), checkfirst=True)
    NotificationOutbox.__table__.drop(op.get_bind(), checkfirst=True)
