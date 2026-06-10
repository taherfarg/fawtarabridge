import uuid

from sqlalchemy import select

from app.models import TenantMembership, User
from app.repositories.base import TenantScopedRepository


class MembershipRepository(TenantScopedRepository[TenantMembership]):
    model = TenantMembership

    def get_by_user(self, user_id: uuid.UUID) -> TenantMembership | None:
        stmt = self.query().where(TenantMembership.user_id == user_id)
        return self.session.scalars(stmt).one_or_none()

    def list_with_users(self) -> list[tuple[TenantMembership, User]]:
        stmt = (
            select(TenantMembership, User)
            .join(User, User.id == TenantMembership.user_id)
            .where(TenantMembership.tenant_id == self.tenant_id)
            .order_by(TenantMembership.created_at)
        )
        return [(m, u) for m, u in self.session.execute(stmt).all()]
