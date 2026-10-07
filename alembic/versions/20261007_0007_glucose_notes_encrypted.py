"""Encrypt free-text glucose record notes."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

from app.core.crypto import encrypt_field

revision = "20261007_0007"
down_revision = "20261006_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    columns = {column["name"] for column in sa.inspect(connection).get_columns("glucose_records")}
    if "notes_encrypted" not in columns:
        op.add_column("glucose_records", sa.Column("notes_encrypted", sa.LargeBinary(), nullable=True))
    columns = {column["name"] for column in sa.inspect(connection).get_columns("glucose_records")}
    if "notes" in columns:
        rows = connection.execute(sa.text("SELECT id, notes FROM glucose_records WHERE notes IS NOT NULL")).all()
        for record_id, notes in rows:
            connection.execute(
                sa.text("UPDATE glucose_records SET notes_encrypted=:ciphertext WHERE id=:id"),
                {"ciphertext": encrypt_field(notes, table="glucose_records", column="notes", record_id=record_id),
                 "id": record_id},
            )
        if connection.dialect.name == "sqlite":
            with op.batch_alter_table("glucose_records", recreate="always") as batch:
                batch.drop_column("notes")
        else:
            op.drop_column("glucose_records", "notes")


def downgrade() -> None:
    raise RuntimeError("Encrypted clinical notes cannot be downgraded without a protected plaintext export.")
