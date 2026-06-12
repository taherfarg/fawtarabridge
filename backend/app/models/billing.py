import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class UsageRecord(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Per-tenant per-month transmission metering (FR-8.2)."""

    __tablename__ = "usage_records"
    __table_args__ = (UniqueConstraint("tenant_id", "period"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    period: Mapped[str] = mapped_column(String(7))  # YYYY-MM
    invoice_count: Mapped[int] = mapped_column(default=0)
    overage_count: Mapped[int] = mapped_column(default=0)
    warned_80: Mapped[bool] = mapped_column(default=False)


class NotificationRecord(Base, UUIDPrimaryKeyMixin):
    """Outbound notification log — the console stubs write here so the UI/tests
    can observe what WOULD have been sent (FR-6)."""

    __tablename__ = "notifications"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    channel: Mapped[str] = mapped_column(String(20))  # whatsapp | email
    recipient: Mapped[str] = mapped_column(String(255))
    template: Mapped[str] = mapped_column(String(50))
    params: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
