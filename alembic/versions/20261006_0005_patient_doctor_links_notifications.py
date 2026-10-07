"""Persist patient-doctor association cycles and internal notifications.

Revision ID: 20261006_0005
Revises: 20261006_0004
Create Date: 2026-10-06
"""

from __future__ import annotations

from alembic import op

from app.models.entities import Notification, PatientDoctorLink


revision = "20261006_0005"
down_revision = "20261006_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    PatientDoctorLink.__table__.create(op.get_bind(), checkfirst=True)
    Notification.__table__.create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    Notification.__table__.drop(op.get_bind(), checkfirst=True)
    PatientDoctorLink.__table__.drop(op.get_bind(), checkfirst=True)
