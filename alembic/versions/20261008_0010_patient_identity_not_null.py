"""Make the encrypted patient identity columns non-null.

Revision ID: 20261008_0010
Revises: 20261008_0009
Create Date: 2026-10-08
"""

from alembic import op
import sqlalchemy as sa

from app.core.crypto import encrypt_field, generate_short_id


revision = "20261008_0010"
down_revision = "20261008_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    columns = {column["name"]: column for column in sa.inspect(connection).get_columns("patients")}
    if "name_encrypted" not in columns or "short_id" not in columns:
        raise RuntimeError("Expected encrypted patient identity columns are missing")

    missing_names = connection.execute(sa.text(
        "SELECT id FROM patients WHERE name_encrypted IS NULL ORDER BY id"
    )).scalars().all()
    for patient_id in missing_names:
        # Legacy plaintext has already been removed by migration 0003. Preserve
        # the row and the model's empty-name behavior when no recoverable value remains.
        connection.execute(sa.text(
            "UPDATE patients SET name_encrypted=:value WHERE id=:id"
        ), {"value": encrypt_field("", table="patients", column="name", record_id=patient_id), "id": patient_id})

    missing_ids = connection.execute(sa.text(
        "SELECT id FROM patients WHERE short_id IS NULL ORDER BY id"
    )).scalars().all()
    occupied = set(connection.execute(sa.text(
        "SELECT short_id FROM patients WHERE short_id IS NOT NULL"
    )).scalars().all())
    for patient_id in missing_ids:
        short_id = generate_short_id(lambda value: value in occupied)
        occupied.add(short_id)
        connection.execute(sa.text(
            "UPDATE patients SET short_id=:value WHERE id=:id"
        ), {"value": short_id, "id": patient_id})

    with op.batch_alter_table("patients") as batch:
        batch.alter_column("name_encrypted", existing_type=sa.LargeBinary(), nullable=False)
        batch.alter_column("short_id", existing_type=sa.String(length=6), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("patients") as batch:
        batch.alter_column("short_id", existing_type=sa.String(length=6), nullable=True)
        batch.alter_column("name_encrypted", existing_type=sa.LargeBinary(), nullable=True)
