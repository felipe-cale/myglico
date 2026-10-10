"""Convert historically stored local wall times to naive UTC.

Revision ID: 20261008_0011
Revises: 20261008_0010
Create Date: 2026-10-08
"""

from alembic import op
from datetime import datetime
import sqlalchemy as sa

from app.core.patient_time import local_datetime_to_utc_naive, patient_local_datetime


revision = "20261008_0011"
down_revision = "20261008_0010"
branch_labels = None
depends_on = None


def _as_datetime(value: datetime | str) -> datetime:
    return datetime.fromisoformat(value) if isinstance(value, str) else value


def upgrade() -> None:
    connection = op.get_bind()
    last_id = ""
    while True:
        batch = connection.execute(sa.text(
            "SELECT glucose_records.id, glucose_records.measured_at, patients.timezone "
            "FROM glucose_records JOIN patients ON patients.id = glucose_records.patient_id "
            "WHERE glucose_records.id > :last_id ORDER BY glucose_records.id LIMIT 1000"
        ), {"last_id": last_id}).all()
        if not batch:
            break
        for record_id, measured_at, timezone_name in batch:
            connection.execute(sa.text(
                "UPDATE glucose_records SET measured_at=:measured_at WHERE id=:record_id"
            ), {
                "measured_at": local_datetime_to_utc_naive(_as_datetime(measured_at), timezone_name),
                "record_id": record_id,
            })
        last_id = batch[-1][0]


def downgrade() -> None:
    connection = op.get_bind()
    last_id = ""
    while True:
        batch = connection.execute(sa.text(
            "SELECT glucose_records.id, glucose_records.measured_at, patients.timezone "
            "FROM glucose_records JOIN patients ON patients.id = glucose_records.patient_id "
            "WHERE glucose_records.id > :last_id ORDER BY glucose_records.id LIMIT 1000"
        ), {"last_id": last_id}).all()
        if not batch:
            break
        for record_id, measured_at, timezone_name in batch:
            connection.execute(sa.text(
                "UPDATE glucose_records SET measured_at=:measured_at WHERE id=:record_id"
            ), {
                "measured_at": patient_local_datetime(_as_datetime(measured_at), timezone_name).replace(tzinfo=None),
                "record_id": record_id,
            })
        last_id = batch[-1][0]
