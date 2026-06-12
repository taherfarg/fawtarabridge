from datetime import date, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app.api.deps import AuthContext, AuthDep, TenantDbDep, require_roles
from app.billing.service import usage_summary
from app.billing.stripe_stub import get_payment_provider
from app.core.errors import AppError
from app.models import Tenant
from app.models.billing import NotificationRecord
from app.models.enums import Role
from app.services import audit_service

router = APIRouter(tags=["billing"])

OwnerCtx = Annotated[AuthContext, Depends(require_roles(Role.OWNER))]
AdminCtx = Annotated[AuthContext, Depends(require_roles(Role.OWNER, Role.ACCOUNTANT))]


class UsageOut(BaseModel):
    plan: str
    price_aed: int
    period: str
    invoice_count: int
    included_invoices: int
    overage_count: int
    overage_rate_aed: int
    overage_charge_aed: int
    warning_80: bool
    trial_ends_at: date | None


class PlanChangeIn(BaseModel):
    plan: Literal["starter", "growth", "accountant"]


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    channel: str
    recipient: str
    template: str
    params: dict[str, Any]
    created_at: datetime


def _tenant(db: TenantDbDep, ctx: AuthContext) -> Tenant:
    tenant = db.get(Tenant, ctx.tenant_id)
    if tenant is None:
        raise AppError("tenant.not_found", status_code=404)
    return tenant


@router.get("/billing/usage", response_model=UsageOut)
def get_usage(db: TenantDbDep, ctx: AuthDep) -> UsageOut:
    return UsageOut(**usage_summary(db, _tenant(db, ctx)))


@router.post("/billing/plan", response_model=UsageOut)
def change_plan(payload: PlanChangeIn, db: TenantDbDep, ctx: OwnerCtx) -> UsageOut:
    tenant = _tenant(db, ctx)
    before = tenant.plan
    tenant.plan = payload.plan
    subscription_id = get_payment_provider().start_subscription(
        tenant_id=tenant.id, plan=payload.plan
    )
    audit_service.record(
        db,
        tenant.id,
        action="tenant.plan_changed",
        entity_type="tenant",
        entity_id=tenant.id,
        actor_id=ctx.user_id,
        before={"plan": before},
        after={"plan": payload.plan, "subscription_id": subscription_id},
    )
    return UsageOut(**usage_summary(db, tenant))


@router.get("/notifications", response_model=list[NotificationOut])
def list_notifications(db: TenantDbDep, ctx: AdminCtx) -> list[NotificationOut]:
    rows = db.scalars(
        select(NotificationRecord)
        .where(NotificationRecord.tenant_id == ctx.tenant_id)
        .order_by(NotificationRecord.created_at.desc())
        .limit(100)
    ).all()
    return [NotificationOut.model_validate(r) for r in rows]
