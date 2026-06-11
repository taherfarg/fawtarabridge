"""Monthly compliance summary (FR-5.1/FR-5.4).

Penalty model from the build instructions: AED 100 per unsent past-due invoice,
capped at AED 5,000 per month. # SPEC-CHECK: confirm exact mechanics against
Cabinet Resolution 106 of 2025 (PRD open question 4); the reporting grace period
(default 2 days) is a setting.
"""

import re
import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.errors import AppError
from app.lifecycle.state_machine import InvoiceStatus
from app.models import Invoice

UNSENT_STATUSES = (
    InvoiceStatus.DRAFT.value,
    InvoiceStatus.VALIDATED.value,
    InvoiceStatus.REJECTED.value,
    InvoiceStatus.ERROR.value,
)

_PERIOD_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def compute_penalty(unsent_past_due_count: int) -> int:
    settings = get_settings()
    return min(
        settings.penalty_per_unsent_invoice_aed * unsent_past_due_count,
        settings.penalty_monthly_cap_aed,
    )


def parse_period(period: str | None) -> tuple[date, date, str]:
    """'YYYY-MM' -> (first day, last day, normalized label); default: current month."""
    if period is None:
        today = date.today()
        period = f"{today.year:04d}-{today.month:02d}"
    if not _PERIOD_RE.fullmatch(period):
        raise AppError("compliance.invalid_period", status_code=422, params={"value": period})
    year, month = int(period[:4]), int(period[5:7])
    first = date(year, month, 1)
    last = (
        date(year + 1, 1, 1) - timedelta(days=1)
        if month == 12
        else date(year, month + 1, 1) - timedelta(days=1)
    )
    return first, last, period


def monthly_summary(db: Session, tenant_id: uuid.UUID, period: str | None) -> dict:
    first, last, label = parse_period(period)
    settings = get_settings()

    rows = db.execute(
        select(Invoice.status, func.count(), func.sum(Invoice.total_including_vat))
        .where(
            Invoice.tenant_id == tenant_id,
            Invoice.issue_date >= first,
            Invoice.issue_date <= last,
        )
        .group_by(Invoice.status)
    ).all()
    counts = {status.value: 0 for status in InvoiceStatus}
    accepted_total = Decimal("0")
    for status, count, total in rows:
        counts[status] = count
        if status == InvoiceStatus.ACCEPTED.value and total is not None:
            accepted_total = total

    past_due_cutoff = date.today() - timedelta(days=settings.reporting_grace_days)
    unsent_past_due = (
        db.scalar(
            select(func.count())
            .select_from(Invoice)
            .where(
                Invoice.tenant_id == tenant_id,
                Invoice.issue_date >= first,
                Invoice.issue_date <= last,
                Invoice.issue_date <= past_due_cutoff,
                Invoice.status.in_(UNSENT_STATUSES),
            )
        )
        or 0
    )

    return {
        "period": label,
        "total_invoices": sum(counts.values()),
        "counts": counts,
        "accepted_total_aed": accepted_total,
        "unsent_past_due": unsent_past_due,
        "penalty_risk_aed": compute_penalty(unsent_past_due),
        "penalty_cap_aed": settings.penalty_monthly_cap_aed,
        "currency": "AED",
    }
