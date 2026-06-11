"""Tenant isolation proven at the PostgreSQL level (row-level security).

These tests use the app role (fawtara_app) with raw sessions and explicit GUCs —
no FastAPI, no repositories — to prove the *database itself* refuses cross-tenant
access even if every application layer above it is buggy.
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import Engine, func, select, update
from sqlalchemy.exc import ProgrammingError

from app.db.session import set_rls_context
from app.models import Tenant, TenantMembership, User
from app.models.enums import Role
from tests.conftest import SessionFactory

TwoTenants = tuple[tuple[uuid.UUID, uuid.UUID], tuple[uuid.UUID, uuid.UUID]]


def test_tenant_context_sees_only_own_rows(
    make_session: SessionFactory, two_tenants: TwoTenants
) -> None:
    (tenant_a, user_a), (tenant_b, _) = two_tenants
    session = make_session()
    set_rls_context(session, tenant_id=tenant_a, user_id=user_a)

    visible_tenants = set(session.scalars(select(Tenant.id)).all())
    assert visible_tenants == {tenant_a}

    # Even an explicit primary-key fetch of the foreign tenant returns nothing.
    assert session.get(Tenant, tenant_b) is None

    membership_tenants = set(session.scalars(select(TenantMembership.tenant_id)).all())
    assert membership_tenants == {tenant_a}


def test_unscoped_query_without_guc_sees_nothing(
    make_session: SessionFactory, two_tenants: TwoTenants
) -> None:
    session = make_session()  # no GUCs set at all
    assert session.scalar(select(func.count()).select_from(Tenant)) == 0
    assert session.scalar(select(func.count()).select_from(TenantMembership)) == 0


def test_cannot_insert_rows_for_foreign_tenant(
    make_session: SessionFactory, two_tenants: TwoTenants
) -> None:
    (tenant_a, user_a), (tenant_b, _) = two_tenants
    session = make_session()
    set_rls_context(session, tenant_id=tenant_a, user_id=user_a)
    session.add(TenantMembership(tenant_id=tenant_b, user_id=user_a, role=Role.STAFF))
    with pytest.raises(ProgrammingError, match="row-level security"):
        session.flush()


def test_cannot_update_foreign_tenant(
    make_session: SessionFactory, two_tenants: TwoTenants, admin_engine: Engine
) -> None:
    (tenant_a, user_a), (tenant_b, _) = two_tenants
    session = make_session()
    set_rls_context(session, tenant_id=tenant_a, user_id=user_a)
    result = session.execute(
        update(Tenant).where(Tenant.id == tenant_b).values(legal_name_en="HACKED")
    )
    assert result.rowcount == 0  # the row is invisible, so nothing matches
    session.commit()

    with admin_engine.connect() as conn:  # admin bypasses RLS: verify ground truth
        name = conn.execute(select(Tenant.legal_name_en).where(Tenant.id == tenant_b)).scalar_one()
    assert name == "Company"


def test_user_arm_exposes_only_own_memberships(
    make_session: SessionFactory, two_tenants: TwoTenants
) -> None:
    """Login flow (user GUC only): a user sees their tenants, nobody else's."""
    (tenant_a, user_a), _ = two_tenants
    session = make_session()
    set_rls_context(session, user_id=user_a)  # no tenant context, like at login

    assert set(session.scalars(select(Tenant.id)).all()) == {tenant_a}
    assert set(session.scalars(select(TenantMembership.tenant_id)).all()) == {tenant_a}


def test_tenant_a_can_never_read_tenant_b_invoices(
    make_session: SessionFactory, two_tenants: TwoTenants
) -> None:
    """THE multi-tenancy promise (architecture rule 2), on the invoices table itself."""
    from app.models import Invoice

    (tenant_a, user_a), (tenant_b, user_b) = two_tenants

    def insert_invoice(tenant_id: uuid.UUID, user_id: uuid.UUID, number: str) -> None:
        session = make_session()
        set_rls_context(session, tenant_id=tenant_id, user_id=user_id)
        session.add(
            Invoice(
                tenant_id=tenant_id,
                invoice_number=number,
                canonical={},
                issue_date=date(2026, 5, 15),
                buyer_name="Buyer",
                total_including_vat=Decimal("105.00"),
                created_by=user_id,
            )
        )
        session.commit()

    insert_invoice(tenant_a, user_a, "A-1")
    insert_invoice(tenant_b, user_b, "B-1")

    session = make_session()
    set_rls_context(session, tenant_id=tenant_a, user_id=user_a)
    visible = list(session.scalars(select(Invoice.invoice_number)).all())
    assert visible == ["A-1"]  # B-1 is invisible even via SELECT *

    # Insert for the foreign tenant is refused by the database itself.
    session.add(
        Invoice(
            tenant_id=tenant_b,
            invoice_number="EVIL-1",
            canonical={},
            issue_date=date(2026, 5, 15),
            buyer_name="X",
            total_including_vat=Decimal("1.00"),
        )
    )
    with pytest.raises(ProgrammingError, match="row-level security"):
        session.flush()


def test_accountant_spanning_tenants_sees_both(
    make_session: SessionFactory, two_tenants: TwoTenants
) -> None:
    (tenant_a, user_a), (tenant_b, user_b) = two_tenants

    # Each owner links the same accountant identity to their own tenant.
    session = make_session()
    accountant_id = uuid.uuid4()
    set_rls_context(session, tenant_id=tenant_a, user_id=user_a)
    session.add(
        User(
            id=accountant_id,
            email="acc@example.com",
            password_hash="x",
            full_name="Accountant",
            phone="+971501111111",
        )
    )
    session.flush()  # user row must exist before the membership FK
    session.add(TenantMembership(tenant_id=tenant_a, user_id=accountant_id, role=Role.ACCOUNTANT))
    session.commit()

    session2 = make_session()
    set_rls_context(session2, tenant_id=tenant_b, user_id=user_b)
    session2.add(TenantMembership(tenant_id=tenant_b, user_id=accountant_id, role=Role.ACCOUNTANT))
    session2.commit()

    session3 = make_session()
    set_rls_context(session3, user_id=accountant_id)
    assert set(session3.scalars(select(Tenant.id)).all()) == {tenant_a, tenant_b}
