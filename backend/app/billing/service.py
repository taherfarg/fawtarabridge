"""Usage metering (FR-8.2). Called from the send path; MUST never block or raise
business errors — billing trouble is never a reason to stop a compliance
transmission."""

import logging
import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.billing.plans import OVERAGE_RATE_AED, PLANS, WARNING_THRESHOLD, Plan
from app.models import Tenant
from app.models.billing import UsageRecord

logger = logging.getLogger(__name__)


def current_period(today: date | None = None) -> str:
    today = today or date.today()
    return f"{today.year:04d}-{today.month:02d}"


def plan_for(tenant: Tenant) -> Plan:
    return PLANS.get(tenant.plan, PLANS["starter"])


def _get_or_create_usage(db: Session, tenant_id: uuid.UUID, period: str) -> UsageRecord:
    usage = db.scalars(
        select(UsageRecord).where(UsageRecord.tenant_id == tenant_id, UsageRecord.period == period)
    ).one_or_none()
    if usage is None:
        usage = UsageRecord(tenant_id=tenant_id, period=period)
        db.add(usage)
        db.flush()
    return usage


def record_transmission_usage(db: Session, tenant: Tenant, *, first_send: bool) -> None:
    """Meter one invoice transmission. Resends of the same invoice are free
    (first_send=False). Crossing 80% of the quota notifies the owners once;
    beyond 100% we count overage (AED 1/invoice) and keep going."""
    if not first_send:
        return
    try:
        plan = plan_for(tenant)
        usage = _get_or_create_usage(db, tenant.id, current_period())
        usage.invoice_count += 1
        if usage.invoice_count > plan.included_invoices:
            usage.overage_count += 1
        elif (
            not usage.warned_80
            and usage.invoice_count >= plan.included_invoices * WARNING_THRESHOLD
        ):
            usage.warned_80 = True
            from app.notifications.service import notify_owners

            notify_owners(
                db,
                tenant.id,
                template="usage_80",
                params={
                    "used": usage.invoice_count,
                    "included": plan.included_invoices,
                    "plan": plan.code,
                },
            )
    except Exception:  # pragma: no cover - belt & braces: metering never blocks
        logger.exception("usage metering failed; transmission proceeds anyway")


def usage_summary(db: Session, tenant: Tenant) -> dict:
    plan = plan_for(tenant)
    period = current_period()
    usage = db.scalars(
        select(UsageRecord).where(UsageRecord.tenant_id == tenant.id, UsageRecord.period == period)
    ).one_or_none()
    count = usage.invoice_count if usage else 0
    overage = usage.overage_count if usage else 0
    return {
        "plan": plan.code,
        "price_aed": plan.price_aed,
        "period": period,
        "invoice_count": count,
        "included_invoices": plan.included_invoices,
        "overage_count": overage,
        "overage_rate_aed": OVERAGE_RATE_AED,
        "overage_charge_aed": overage * OVERAGE_RATE_AED,
        "warning_80": usage.warned_80 if usage else False,
        "trial_ends_at": tenant.trial_ends_at,
    }
