"""Store immutable encrypted snapshots for each reviewed proposal version."""

from alembic import op
import sqlalchemy as sa

revision = "20261013_0015"
down_revision = "20261013_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "glico_proposal_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("proposal_id", sa.String(36), sa.ForeignKey("glico_proposals.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("context_version", sa.Integer(), nullable=False),
        sa.Column("payload_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("proposal_id", "version", name="uq_glico_proposal_revision_version"),
    )
    op.create_index("ix_glico_proposal_revisions_proposal_id", "glico_proposal_revisions", ["proposal_id"])
    # Preserve the current version of rows created before this forward migration.
    op.execute(sa.text("""INSERT INTO glico_proposal_revisions
        (id, proposal_id, version, context_version, payload_encrypted, digest, created_at)
        SELECT id, id, version, context_version, payload_encrypted, digest, created_at FROM glico_proposals"""))


def downgrade() -> None:
    op.drop_index("ix_glico_proposal_revisions_proposal_id", table_name="glico_proposal_revisions")
    op.drop_table("glico_proposal_revisions")
