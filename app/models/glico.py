from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import CheckConstraint, ForeignKey, Integer, LargeBinary, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _uuid() -> str:
    return str(uuid4())


def _now() -> datetime:
    return datetime.utcnow()


class GlicoConversation(Base):
    __tablename__ = "glico_conversations"
    __table_args__ = (UniqueConstraint("owner_account_id", "client_request_id", name="uq_glico_conversation_client_request"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    owner_account_id: Mapped[str] = mapped_column(ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    client_request_id: Mapped[str] = mapped_column(String(36), nullable=False)
    patient_id: Mapped[str | None] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), index=True)
    association_id: Mapped[str | None] = mapped_column(ForeignKey("patient_doctor_links.id", ondelete="SET NULL"), index=True)
    context_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    locale: Mapped[str] = mapped_column(String(8), nullable=False)
    period_start: Mapped[str | None] = mapped_column(String(10))
    period_end: Mapped[str | None] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(default=_now, onupdate=_now, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(nullable=False, index=True)


class GlicoProposal(Base):
    __tablename__ = "glico_proposals"
    __table_args__ = (
        CheckConstraint("version >= 1", name="ck_glico_proposal_version"),
        CheckConstraint("state IN ('DRAFT','READY','EXECUTED','CANCELLED','EXPIRED','INVALIDATED')", name="ck_glico_proposal_state"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("glico_conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    owner_account_id: Mapped[str] = mapped_column(ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    association_id: Mapped[str | None] = mapped_column(ForeignKey("patient_doctor_links.id", ondelete="SET NULL"), index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    context_version: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="DRAFT", index=True)
    payload_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    digest: Mapped[str] = mapped_column(String(64), nullable=False)
    origin: Mapped[str] = mapped_column(String(32), nullable=False)
    engine_version: Mapped[str | None] = mapped_column(String(120))
    expires_at: Mapped[datetime] = mapped_column(nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(default=_now, onupdate=_now, nullable=False)


class GlicoProposalRevision(Base):
    """Immutable encrypted snapshot for every user reviewed proposal version."""
    __tablename__ = "glico_proposal_revisions"
    __table_args__ = (UniqueConstraint("proposal_id", "version", name="uq_glico_proposal_revision_version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    proposal_id: Mapped[str] = mapped_column(ForeignKey("glico_proposals.id", ondelete="CASCADE"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    context_version: Mapped[int] = mapped_column(Integer, nullable=False)
    payload_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=_now, nullable=False)


class GlicoExecution(Base):
    __tablename__ = "glico_executions"
    __table_args__ = (
        UniqueConstraint("proposal_id", "proposal_version", name="uq_glico_execution_proposal_version"),
        UniqueConstraint("owner_account_id", "operation", "idempotency_digest", name="uq_glico_execution_idempotency"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    proposal_id: Mapped[str] = mapped_column(ForeignKey("glico_proposals.id", ondelete="RESTRICT"), nullable=False)
    proposal_version: Mapped[int] = mapped_column(Integer, nullable=False)
    owner_account_id: Mapped[str] = mapped_column(ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False)
    operation: Mapped[str] = mapped_column(String(32), nullable=False)
    idempotency_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    result_type: Mapped[str] = mapped_column(String(32), nullable=False)
    result_id: Mapped[str | None] = mapped_column(String(36))
    analytics_status: Mapped[str] = mapped_column(String(24), nullable=False, default="not_applicable")
    committed_at: Mapped[datetime] = mapped_column(default=_now, nullable=False)


class GlicoQuotaBucket(Base):
    __tablename__ = "glico_quota_buckets"
    __table_args__ = (
        UniqueConstraint("owner_account_id", "bucket", "window_start", name="uq_glico_quota_owner_bucket_window"),
        CheckConstraint("used >= 0", name="ck_glico_quota_used_nonnegative"),
        CheckConstraint("reserved >= 0", name="ck_glico_quota_reserved_nonnegative"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    owner_account_id: Mapped[str] = mapped_column(ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False)
    bucket: Mapped[str] = mapped_column(String(32), nullable=False)
    window_start: Mapped[datetime] = mapped_column(nullable=False)
    used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reserved: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(default=_now, onupdate=_now, nullable=False)


class GlicoGlobalQuota(Base):
    __tablename__ = "glico_global_quotas"
    bucket: Mapped[str] = mapped_column(String(32), primary_key=True)
    reserved: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(default=_now, onupdate=_now, nullable=False)


class GlicoRequestReplay(Base):
    __tablename__ = "glico_request_replays"
    __table_args__ = (UniqueConstraint("owner_account_id", "operation", "client_request_id",
                                       name="uq_glico_request_replay_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("glico_conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    owner_account_id: Mapped[str] = mapped_column(ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    operation: Mapped[str] = mapped_column(String(16), nullable=False)
    client_request_id: Mapped[str] = mapped_column(String(36), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    response_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(default=_now, nullable=False)



