import uuid

from sqlalchemy import Enum, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.pintae.canonical import VatCategory


class Contact(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Buyer/customer address book entry (FR-2.3). Tenant-scoped, RLS-protected.

    TRN is optional at the contact level (it may be unknown when the contact is
    first saved); invoice validation enforces buyer-TRN presence at invoice level.
    """

    __tablename__ = "contacts"
    __table_args__ = (
        # One contact per TRN per tenant — prevents accidental duplicates.
        Index(
            "ix_contacts_tenant_id_trn",
            "tenant_id",
            "trn",
            unique=True,
            postgresql_where="trn IS NOT NULL",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    name_en: Mapped[str] = mapped_column(String(255))
    name_ar: Mapped[str | None] = mapped_column(String(255))
    trn: Mapped[str | None] = mapped_column(String(15))
    peppol_id: Mapped[str | None] = mapped_column(String(100))
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(20))
    street: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(100))
    emirate: Mapped[str | None] = mapped_column(String(50))
    country_code: Mapped[str] = mapped_column(String(2), default="AE")
    default_vat_category: Mapped[VatCategory | None] = mapped_column(
        Enum(
            VatCategory, native_enum=False, length=4, values_callable=lambda e: [m.value for m in e]
        )
    )
