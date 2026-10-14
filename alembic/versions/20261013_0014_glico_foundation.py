"""Create the secure Glico conversation, proposal, receipt and quota core."""

from alembic import op
import sqlalchemy as sa

revision = "20261013_0014"
down_revision = "20261012_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "glico_conversations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_account_id", sa.String(36), sa.ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("client_request_id", sa.String(36), nullable=False),
        sa.Column("patient_id", sa.String(36), sa.ForeignKey("patients.id", ondelete="CASCADE"), nullable=True),
        sa.Column("association_id", sa.String(36), sa.ForeignKey("patient_doctor_links.id", ondelete="SET NULL"), nullable=True),
        sa.Column("context_version", sa.Integer(), nullable=False),
        sa.Column("locale", sa.String(8), nullable=False),
        sa.Column("period_start", sa.String(10), nullable=True),
        sa.Column("period_end", sa.String(10), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("owner_account_id", "client_request_id", name="uq_glico_conversation_client_request"),
    )
    op.create_index("ix_glico_conversations_owner_account_id", "glico_conversations", ["owner_account_id"])
    op.create_index("ix_glico_conversations_patient_id", "glico_conversations", ["patient_id"])
    op.create_index("ix_glico_conversations_association_id", "glico_conversations", ["association_id"])
    op.create_index("ix_glico_conversations_expires_at", "glico_conversations", ["expires_at"])

    op.create_table(
        "glico_proposals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("glico_conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("owner_account_id", sa.String(36), sa.ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("patient_id", sa.String(36), sa.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("association_id", sa.String(36), sa.ForeignKey("patient_doctor_links.id", ondelete="SET NULL"), nullable=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("context_version", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("payload_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("origin", sa.String(32), nullable=False),
        sa.Column("engine_version", sa.String(120), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_glico_proposal_version"),
        sa.CheckConstraint("state IN ('DRAFT','READY','EXECUTED','CANCELLED','EXPIRED','INVALIDATED')", name="ck_glico_proposal_state"),
    )
    for column in ("conversation_id", "owner_account_id", "patient_id", "association_id", "state", "expires_at"):
        op.create_index(f"ix_glico_proposals_{column}", "glico_proposals", [column])

    op.create_table(
        "glico_executions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("proposal_id", sa.String(36), sa.ForeignKey("glico_proposals.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("proposal_version", sa.Integer(), nullable=False),
        sa.Column("owner_account_id", sa.String(36), sa.ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("operation", sa.String(32), nullable=False),
        sa.Column("idempotency_digest", sa.String(64), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("result_type", sa.String(32), nullable=False),
        sa.Column("result_id", sa.String(36), nullable=True),
        sa.Column("analytics_status", sa.String(24), nullable=False),
        sa.Column("committed_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("proposal_id", "proposal_version", name="uq_glico_execution_proposal_version"),
        sa.UniqueConstraint("owner_account_id", "operation", "idempotency_digest", name="uq_glico_execution_idempotency"),
    )

    op.create_table(
        "glico_quota_buckets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_account_id", sa.String(36), sa.ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("bucket", sa.String(32), nullable=False),
        sa.Column("window_start", sa.DateTime(), nullable=False),
        sa.Column("used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reserved", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("owner_account_id", "bucket", "window_start", name="uq_glico_quota_owner_bucket_window"),
        sa.CheckConstraint("used >= 0", name="ck_glico_quota_used_nonnegative"),
        sa.CheckConstraint("reserved >= 0", name="ck_glico_quota_reserved_nonnegative"),
    )
    op.create_index("ix_glico_quota_buckets_owner_account_id", "glico_quota_buckets", ["owner_account_id"])


def downgrade() -> None:
    op.drop_index("ix_glico_quota_buckets_owner_account_id", table_name="glico_quota_buckets")
    op.drop_table("glico_quota_buckets")
    op.drop_table("glico_executions")
    for column in ("conversation_id", "owner_account_id", "patient_id", "association_id", "state", "expires_at"):
        op.drop_index(f"ix_glico_proposals_{column}", table_name="glico_proposals")
    op.drop_table("glico_proposals")
    for column in ("owner_account_id", "patient_id", "association_id", "expires_at"):
        op.drop_index(f"ix_glico_conversations_{column}", table_name="glico_conversations")
    op.drop_table("glico_conversations")



