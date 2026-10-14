"""Add database shared serialization for expensive Glico media jobs."""

from datetime import datetime

from alembic import op
import sqlalchemy as sa

revision = "20261013_0016"
down_revision = "20261013_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "glico_global_quotas",
        sa.Column("bucket", sa.String(32), primary_key=True),
        sa.Column("reserved", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("reserved >= 0", name="ck_glico_global_quota_reserved_nonnegative"),
    )
    op.execute(sa.text("INSERT INTO glico_global_quotas (bucket, reserved, updated_at) VALUES ('image', 0, :now)")
               .bindparams(now=datetime.utcnow()))
    op.execute(sa.text("INSERT INTO glico_global_quotas (bucket, reserved, updated_at) VALUES ('audio', 0, :now)")
               .bindparams(now=datetime.utcnow()))


def downgrade() -> None:
    op.drop_table("glico_global_quotas")
