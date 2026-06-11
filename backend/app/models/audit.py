import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin


class AuditEvent(Base, UUIDPrimaryKeyMixin):
    """Append-only audit log (architecture rule 5).

    Immutability is enforced at the DATABASE level: the app role is granted
    SELECT and INSERT only — UPDATE/DELETE are impossible even for buggy code
    (see migration 0003). No updated_at column by design.
    """

    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_events_entity", "tenant_id", "entity_type", "entity_id"),)

    # Monotonic insertion order: events inside one transaction share created_at
    # (Postgres now() is transaction start), so timestamps alone can't sort them.
    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=True), unique=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    action: Mapped[str] = mapped_column(String(50))
    entity_type: Mapped[str] = mapped_column(String(30))
    entity_id: Mapped[uuid.UUID]
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    actor_type: Mapped[str] = mapped_column(String(20), default="user")  # user|system|asp_webhook
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
