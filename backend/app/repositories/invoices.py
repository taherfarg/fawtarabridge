import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from app.models import Invoice
from app.repositories.base import TenantScopedRepository

DUPLICATE_WINDOW_DAYS = 3


class InvoiceRepository(TenantScopedRepository[Invoice]):
    model = Invoice

    def list_filtered(
        self,
        *,
        status: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        buyer: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Invoice], int]:
        stmt = self.query()
        if status:
            stmt = stmt.where(Invoice.status == status)
        if date_from:
            stmt = stmt.where(Invoice.issue_date >= date_from)
        if date_to:
            stmt = stmt.where(Invoice.issue_date <= date_to)
        if buyer:
            pattern = f"%{buyer}%"
            stmt = stmt.where(
                Invoice.buyer_name.ilike(pattern) | Invoice.buyer_trn.like(f"{buyer}%")
            )
        total = self.session.scalar(
            select(func.count()).select_from(stmt.order_by(None).subquery())
        )
        items = list(
            self.session.scalars(
                stmt.order_by(Invoice.issue_date.desc(), Invoice.created_at.desc())
                .limit(limit)
                .offset(offset)
            ).all()
        )
        return items, int(total or 0)

    def find_duplicates(
        self,
        *,
        buyer_trn: str | None,
        buyer_name: str,
        total_including_vat: Decimal,
        issue_date: date,
        exclude_id: uuid.UUID | None = None,
    ) -> list[Invoice]:
        """FR-2.5: same buyer + same amount + issue date within ±3 days."""
        window = timedelta(days=DUPLICATE_WINDOW_DAYS)
        stmt = self.query().where(
            Invoice.total_including_vat == total_including_vat,
            Invoice.issue_date >= issue_date - window,
            Invoice.issue_date <= issue_date + window,
        )
        if buyer_trn:
            stmt = stmt.where(Invoice.buyer_trn == buyer_trn)
        else:
            stmt = stmt.where(Invoice.buyer_name == buyer_name)
        if exclude_id is not None:
            stmt = stmt.where(Invoice.id != exclude_id)
        return list(self.session.scalars(stmt.order_by(Invoice.issue_date)).all())
