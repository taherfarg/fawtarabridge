import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Date, DateTime, ForeignKey, Index, LargeBinary, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin


class ArchiveRecord(Base, UUIDPrimaryKeyMixin):
    """Immutable archive of a cleared invoice: exact XML, rendered PDF, ASP
    acknowledgement (FR-7.1). Append-only via DB grants (SELECT+INSERT only),
    like audit_events. No updated_at by design.

    Blobs live inline for the MVP; production swaps to UAE-region WORM object
    storage behind the archive service without touching callers (D-041).
    """

    __tablename__ = "archive_records"
    __table_args__ = (Index("ix_archive_records_tenant_issue", "tenant_id", "issue_date"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), index=True
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("invoices.id", ondelete="RESTRICT"), unique=True
    )
    transmission_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("transmissions.id", ondelete="SET NULL")
    )
    # Denormalized for search/export without touching the blobs.
    invoice_number: Mapped[str] = mapped_column(String(100))
    buyer_name: Mapped[str] = mapped_column(String(255))
    buyer_trn: Mapped[str | None] = mapped_column(String(15))
    issue_date: Mapped[date] = mapped_column(Date)
    total_including_vat: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    spec_version: Mapped[str] = mapped_column(String(30))
    xml: Mapped[bytes] = mapped_column(LargeBinary)
    pdf: Mapped[bytes] = mapped_column(LargeBinary)
    ack: Mapped[dict[str, Any]] = mapped_column(JSONB)
    xml_hash: Mapped[str] = mapped_column(String(64))
    retention_until: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
