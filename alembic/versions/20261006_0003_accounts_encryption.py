"""Add foundational account and doctor models, encrypt patient identity fields.

Revision ID: 20261006_0003
Revises: 20260504_0002
Create Date: 2026-10-06
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

from app.core.crypto import encrypt_field, generate_short_id


revision = "20261006_0003"
down_revision = "20260504_0002"
branch_labels = None
depends_on = None


def _columns(connection, table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(connection).get_columns(table_name)}


def _create_account_tables() -> None:
    # Frozen DDL: mirrors the UserAccount/Doctor models as of this revision and
    # must never be derived from the current ORM metadata.
    op.create_table(
        "user_accounts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("email_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column("email_lookup", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column("account_status", sa.String(length=32), nullable=False),
        sa.Column("email_verified_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("is_demo", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email_lookup", name="uq_user_accounts_email_lookup"),
    )
    op.create_table(
        "doctors",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("short_id", sa.String(length=6), nullable=False),
        sa.Column("user_account_id", sa.String(length=36), nullable=False),
        sa.Column("name_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column("crm_encrypted", sa.LargeBinary(), nullable=True),
        sa.Column("uf_encrypted", sa.LargeBinary(), nullable=True),
        sa.Column("crm_uf_lookup", sa.String(length=64), nullable=True),
        sa.Column("is_demo", sa.Boolean(), nullable=False),
        sa.Column("declared_verified", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_account_id"], ["user_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("short_id", name="uq_doctors_short_id"),
        sa.UniqueConstraint("user_account_id", name="uq_doctors_user_account_id"),
        sa.UniqueConstraint("crm_uf_lookup", name="uq_doctors_crm_uf_lookup"),
    )


def upgrade() -> None:
    connection = op.get_bind()
    # Create only the new tables, preserving every existing table and row.
    _create_account_tables()

    patient_columns = _columns(connection, "patients")
    if "name_encrypted" not in patient_columns:
        op.add_column("patients", sa.Column("name_encrypted", sa.LargeBinary(), nullable=True))
    if "email_encrypted" not in patient_columns:
        op.add_column("patients", sa.Column("email_encrypted", sa.LargeBinary(), nullable=True))
    if "short_id" not in patient_columns:
        op.add_column("patients", sa.Column("short_id", sa.String(length=6), nullable=True))
    if "user_account_id" not in patient_columns:
        account_column = sa.Column("user_account_id", sa.String(length=36), nullable=True)
        if connection.dialect.name != "sqlite":
            account_column.append_foreign_key(sa.ForeignKey("user_accounts.id"))
        op.add_column("patients", account_column)

    current_columns = _columns(connection, "patients")
    has_legacy_plaintext = "name" in current_columns
    if has_legacy_plaintext:
        rows = connection.execute(sa.text("SELECT id, name, email FROM patients ORDER BY id")).mappings().all()
        occupied: set[str] = set()
        for row in rows:
            short_id = generate_short_id(lambda value: value in occupied)
            occupied.add(short_id)
            name_ciphertext = encrypt_field(
                row["name"], table="patients", column="name", record_id=row["id"]
            )
            email_ciphertext = encrypt_field(
                row["email"], table="patients", column="email", record_id=row["id"]
            )
            connection.execute(
                sa.text(
                    "UPDATE patients SET name_encrypted=:name_encrypted, "
                    "email_encrypted=:email_encrypted, short_id=:short_id WHERE id=:id"
                ),
                {
                    "name_encrypted": name_ciphertext,
                    "email_encrypted": email_ciphertext,
                    "short_id": short_id,
                    "id": row["id"],
                },
            )
    else:
        # A partially applied migration remains recoverable without replacing IDs.
        empty_ids = connection.execute(sa.text("SELECT id FROM patients WHERE short_id IS NULL ORDER BY id")).all()
        occupied = {
            row[0] for row in connection.execute(sa.text("SELECT short_id FROM patients WHERE short_id IS NOT NULL"))
        }
        for (patient_id,) in empty_ids:
            short_id = generate_short_id(lambda value: value in occupied)
            occupied.add(short_id)
            connection.execute(
                sa.text("UPDATE patients SET short_id=:short_id WHERE id=:id"),
                {"short_id": short_id, "id": patient_id},
            )

    indexes = {index["name"] for index in sa.inspect(connection).get_indexes("patients")}
    constraint_columns = {
        tuple(constraint.get("column_names", []))
        for constraint in sa.inspect(connection).get_unique_constraints("patients")
    }
    missing_uniques = [
        (name, column)
        for name, column in (("uq_patients_short_id", "short_id"), ("uq_patients_user_account_id", "user_account_id"))
        if name not in indexes and (column,) not in constraint_columns
    ]
    # SQLite rebuilds the table below, so the uniques become table constraints
    # there, matching the model's UniqueConstraint; elsewhere a unique index is
    # the same object as a unique constraint.
    sqlite_rebuild = has_legacy_plaintext and connection.dialect.name == "sqlite"
    if not sqlite_rebuild:
        for name, column in missing_uniques:
            op.create_index(name, "patients", [column], unique=True)

    # Plaintext columns are dropped only after every row has been encrypted.
    if has_legacy_plaintext:
        for index in sa.inspect(connection).get_indexes("patients"):
            is_unique = bool(index.get("unique"))
            should_drop = {"name", "email"}.intersection(index.get("column_names", []))
            if should_drop and (connection.dialect.name == "sqlite" or not is_unique):
                op.drop_index(index["name"], table_name="patients")
        if connection.dialect.name == "sqlite":
            reflect_args = []
            if "user_account_id" not in patient_columns:
                # Unnamed FK, like the model's ForeignKey and the non-SQLite path;
                # batch create_foreign_key would require a constraint name.
                reflect_args.append(
                    sa.Column(
                        "user_account_id", sa.String(length=36), sa.ForeignKey("user_accounts.id"), nullable=True
                    )
                )
            with op.batch_alter_table("patients", recreate="always", reflect_args=reflect_args) as batch_op:
                batch_op.drop_column("name")
                batch_op.drop_column("email")
                for name, column in missing_uniques:
                    batch_op.create_unique_constraint(name, [column])
        else:
            for constraint in sa.inspect(connection).get_unique_constraints("patients"):
                if "email" in constraint.get("column_names", []) and constraint.get("name"):
                    batch_op = op.batch_alter_table("patients")
                    with batch_op as alter_op:
                        alter_op.drop_constraint(constraint["name"], type_="unique")
                    break
            op.drop_column("patients", "name")
            op.drop_column("patients", "email")


def downgrade() -> None:
    connection = op.get_bind()
    # The encrypted payloads are retained on downgrade; restoring plaintext
    # would require keys and would reintroduce sensitive columns.
    raise RuntimeError(
        "This privacy migration cannot be downgraded safely; restore a protected database backup instead."
    )
