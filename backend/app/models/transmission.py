import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

# Transmission status values (not the invoice lifecycle — see state_machine.py):
# pending -> sent -> accepted | rejected
#         -> failed       (permanent ASP error / invalid content)
#         -> dead_letter  (transient errors exhausted all retries)
TRANSMISSION_TERMINAL_STATUSES = ("accepted", "rejected", "failed", "dead_letter")


class Transmission(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "transmissions"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE"), index=True
    )
    # Travels to the ASP with every send so network-level retries can never
    # double-deliver. Format: "<tenant_id>:<invoice_id>:<xml-hash16>:<ordinal>"
    # — the webhook handler derives the tenant RLS context from it.
    idempotency_key: Mapped[str] = mapped_column(String(120), unique=True)
    asp_provider: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    attempt_count: Mapped[int] = mapped_column(default=0)
    spec_version: Mapped[str] = mapped_column(String(30))
    xml_hash: Mapped[str] = mapped_column(String(64))
    asp_message_id: Mapped[str | None] = mapped_column(String(100), index=True)
    last_error: Mapped[str | None] = mapped_column(Text)
    rejection_code: Mapped[str | None] = mapped_column(String(50))
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
