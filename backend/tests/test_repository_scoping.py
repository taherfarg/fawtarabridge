"""Query-layer isolation: TenantScopedRepository enforces scope independent of RLS."""

import uuid

import pytest
from sqlalchemy.orm import Session

from app.db.session import set_rls_context
from app.models import TenantMembership, User
from app.models.enums import Role
from app.repositories.base import TenantScopedRepository, TenantScopeError
from app.repositories.memberships import MembershipRepository
from tests.conftest import SessionFactory, create_tenant_with_owner


def test_repository_requires_tenant_id(db_session: Session) -> None:
    with pytest.raises(TenantScopeError):
        MembershipRepository(db_session, None)  # type: ignore[arg-type]


def test_repository_rejects_models_without_tenant_id(db_session: Session) -> None:
    class UserRepository(TenantScopedRepository[User]):
        model = User

    with pytest.raises(TenantScopeError):
        UserRepository(db_session, uuid.uuid4())


def test_add_rejects_entity_bound_to_foreign_tenant(db_session: Session) -> None:
    tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
    repo = MembershipRepository(db_session, tenant_a)
    foreign = TenantMembership(tenant_id=tenant_b, user_id=uuid.uuid4(), role=Role.STAFF)
    with pytest.raises(TenantScopeError, match="foreign tenant"):
        repo.add(foreign)


def test_add_stamps_tenant_id(db_session: Session) -> None:
    tenant_a = uuid.uuid4()
    repo = MembershipRepository(db_session, tenant_a)
    entity = repo.add(TenantMembership(user_id=uuid.uuid4(), role=Role.STAFF))
    assert entity.tenant_id == tenant_a


def test_repository_filters_even_when_rls_would_show_more(make_session: SessionFactory) -> None:
    """An accountant's user-arm GUC exposes rows of several tenants at the RLS level;
    the repository must still return only the tenant it was scoped to."""
    tenant_a, user_a = create_tenant_with_owner(
        make_session, trn="100000000000011", email="ra@example.com"
    )
    tenant_b, user_b = create_tenant_with_owner(
        make_session, trn="100000000000012", email="rb@example.com"
    )

    accountant_id = uuid.uuid4()
    s1 = make_session()
    set_rls_context(s1, tenant_id=tenant_a, user_id=user_a)
    s1.add(
        User(
            id=accountant_id,
            email="racc@example.com",
            password_hash="x",
            full_name="Acc",
            phone="+971501111122",
        )
    )
    s1.flush()  # user row must exist before the membership FK
    s1.add(TenantMembership(tenant_id=tenant_a, user_id=accountant_id, role=Role.ACCOUNTANT))
    s1.commit()

    s2 = make_session()
    set_rls_context(s2, tenant_id=tenant_b, user_id=user_b)
    s2.add(TenantMembership(tenant_id=tenant_b, user_id=accountant_id, role=Role.ACCOUNTANT))
    s2.commit()

    s3 = make_session()
    set_rls_context(s3, user_id=accountant_id)  # RLS user arm: both tenants visible
    rows = MembershipRepository(s3, tenant_a).list()
    assert {m.tenant_id for m in rows} == {tenant_a}
