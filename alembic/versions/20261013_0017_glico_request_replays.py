"""Persist bounded idempotency receipts for Glico requests."""

from alembic import op
import sqlalchemy as sa

revision = "20261013_0017"
down_revision = "20261013_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "glico_request_replays",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("glico_conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("owner_account_id", sa.String(36), sa.ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("operation", sa.String(16), nullable=False),
        sa.Column("client_request_id", sa.String(36), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("response_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("owner_account_id", "operation", "client_request_id", name="uq_glico_request_replay_key"),
    )
    op.create_index("ix_glico_request_replays_conversation_id", "glico_request_replays", ["conversation_id"])
    op.create_index("ix_glico_request_replays_owner_account_id", "glico_request_replays", ["owner_account_id"])
    op.create_index("ix_glico_request_replays_expires_at", "glico_request_replays", ["expires_at"])


def downgrade() -> None:
    op.drop_table("glico_request_replays")
