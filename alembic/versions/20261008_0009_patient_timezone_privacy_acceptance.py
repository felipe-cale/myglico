"""Store patient time zones and doctor privacy notice acceptance.

Revision ID: 20261008_0009
Revises: 20261007_0008
Create Date: 2026-10-08
"""

from alembic import op
import sqlalchemy as sa


revision = "20261008_0009"
down_revision = "20261007_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    patient_columns = {column["name"] for column in inspector.get_columns("patients")}
    if "timezone" not in patient_columns:
        op.add_column("patients", sa.Column(
            "timezone", sa.String(length=64), nullable=False, server_default="America/Sao_Paulo",
        ))
        # The server default only backfills existing rows; the model sets the
        # value in the application, so fresh and upgraded schemas must match.
        with op.batch_alter_table("patients") as batch:
            batch.alter_column(
                "timezone", existing_type=sa.String(length=64), existing_nullable=False, server_default=None,
            )
    account_columns = {column["name"] for column in inspector.get_columns("user_accounts")}
    if "privacy_notice_accepted_at" not in account_columns:
        op.add_column("user_accounts", sa.Column("privacy_notice_accepted_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "privacy_notice_accepted_at" in {column["name"] for column in inspector.get_columns("user_accounts")}:
        op.drop_column("user_accounts", "privacy_notice_accepted_at")
    if "timezone" in {column["name"] for column in inspector.get_columns("patients")}:
        op.drop_column("patients", "timezone")
