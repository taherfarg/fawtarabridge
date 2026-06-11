import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import Date, ForeignKey, Index, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Invoice(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Outbound invoice. The CanonicalInvoice JSON is the source of truth; the
    scalar columns are denormalized copies for listing/filtering/duplicate checks.

    Status in M3 is only DRAFT/VALIDATED — the full state machine (QUEUED→SENT→…)
    arrives with the transmission layer in M4.
    """

    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("tenant_id", "invoice_number"),
        Index("ix_invoices_tenant_id_issue_date", "tenant_id", "issue_date"),
        Index("ix_invoices_tenant_id_status", "tenant_id", "status"),
        Index("ix_invoices_tenant_id_buyer_trn", "tenant_id", "buyer_trn"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    invoice_number: Mapped[str] = mapped_column(String(100))
    direction: Mapped[str] = mapped_column(String(10), default="outbound")
    status: Mapped[str] = mapped_column(String(20), default="DRAFT")
    canonical: Mapped[dict[str, Any]] = mapped_column(JSONB)
    spec_version: Mapped[str | None] = mapped_column(String(30))
    buyer_contact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("contacts.id", ondelete="SET NULL")
    )
    # Denormalized from canonical for queries; engine-computed, never user-set.
    issue_date: Mapped[date] = mapped_column(Date)
    buyer_name: Mapped[str] = mapped_column(String(255))
    buyer_trn: Mapped[str | None] = mapped_column(String(15))
    total_including_vat: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    duplicate_warning: Mapped[bool] = mapped_column(default=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class ImportMappingTemplate(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Saved column-mapping per tenant (FR-2.1)."""

    __tablename__ = "import_mapping_templates"
    __table_args__ = (UniqueConstraint("tenant_id", "name"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    mapping: Mapped[dict[str, Any]] = mapped_column(JSONB)
