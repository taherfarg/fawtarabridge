from datetime import date

from sqlalchemy import func, select

from app.models.archive import ArchiveRecord
from app.repositories.base import TenantScopedRepository


class ArchiveRepository(TenantScopedRepository[ArchiveRecord]):
    model = ArchiveRecord

    def search(
        self,
        *,
        query: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ArchiveRecord], int]:
        stmt = self.query()
        if query:
            pattern = f"%{query}%"
            stmt = stmt.where(
                ArchiveRecord.invoice_number.ilike(pattern)
                | ArchiveRecord.buyer_name.ilike(pattern)
                | ArchiveRecord.buyer_trn.like(f"{query}%")
            )
        if date_from:
            stmt = stmt.where(ArchiveRecord.issue_date >= date_from)
        if date_to:
            stmt = stmt.where(ArchiveRecord.issue_date <= date_to)
        total = self.session.scalar(
            select(func.count()).select_from(stmt.order_by(None).subquery())
        )
        items = list(
            self.session.scalars(
                stmt.order_by(ArchiveRecord.issue_date.desc(), ArchiveRecord.created_at.desc())
                .limit(limit)
                .offset(offset)
            ).all()
        )
        return items, int(total or 0)

    def for_export(
        self, *, date_from: date | None = None, date_to: date | None = None
    ) -> list[ArchiveRecord]:
        stmt = self.query()
        if date_from:
            stmt = stmt.where(ArchiveRecord.issue_date >= date_from)
        if date_to:
            stmt = stmt.where(ArchiveRecord.issue_date <= date_to)
        return list(self.session.scalars(stmt.order_by(ArchiveRecord.issue_date)).all())
