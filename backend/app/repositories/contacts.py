from sqlalchemy import func, or_, select

from app.models import Contact
from app.repositories.base import TenantScopedRepository


class ContactRepository(TenantScopedRepository[Contact]):
    model = Contact

    def search(self, query: str | None, *, limit: int, offset: int) -> tuple[list[Contact], int]:
        stmt = self.query()
        if query:
            pattern = f"%{query}%"
            stmt = stmt.where(
                or_(
                    Contact.name_en.ilike(pattern),
                    Contact.name_ar.ilike(pattern),
                    Contact.trn.like(f"{query}%"),
                )
            )
        total = self.session.scalar(
            select(func.count()).select_from(stmt.order_by(None).subquery())
        )
        items = list(
            self.session.scalars(stmt.order_by(Contact.name_en).limit(limit).offset(offset)).all()
        )
        return items, int(total or 0)

    def get_by_trn(self, trn: str) -> Contact | None:
        return self.session.scalars(self.query().where(Contact.trn == trn)).one_or_none()
