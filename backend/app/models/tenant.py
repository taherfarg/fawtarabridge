from datetime import date

from sqlalchemy import Date, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import RevenueBand


class Tenant(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "tenants"

    legal_name_ar: Mapped[str] = mapped_column(String(255))
    legal_name_en: Mapped[str] = mapped_column(String(255))
    trn: Mapped[str] = mapped_column(String(15), unique=True, index=True)
    license_no: Mapped[str | None] = mapped_column(String(100))
    emirate: Mapped[str | None] = mapped_column(String(50))
    address: Mapped[str | None] = mapped_column(String(500))
    revenue_band: Mapped[RevenueBand] = mapped_column(
        Enum(
            RevenueBand,
            native_enum=False,
            length=20,
            values_callable=lambda e: [m.value for m in e],
        ),
        default=RevenueBand.UNKNOWN,
    )
    status: Mapped[str] = mapped_column(String(20), default="active")
    # Peppol participant onboarding via the ASP (FR-1.3); set by the worker task.
    asp_participant_id: Mapped[str | None] = mapped_column(String(100))
    asp_onboarding_status: Mapped[str] = mapped_column(
        String(20), default="not_started"
    )  # not_started | pending | registered | failed
    plan: Mapped[str] = mapped_column(String(20), default="starter")
    trial_ends_at: Mapped[date | None] = mapped_column(Date)
