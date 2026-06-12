"""Celery tasks. Logic lives in services; tasks only add queue semantics."""

import uuid

from app.db.session import get_sessionmaker, tenant_session
from app.models import Tenant
from app.services import audit_service
from app.services.transmission_service import backoff_seconds, execute_transmission
from app.worker.celery_app import celery_app


@celery_app.task(bind=True, name="app.transmit_invoice")
def transmit_invoice(self, transmission_id: str, tenant_id: str) -> str:  # type: ignore[no-untyped-def]
    outcome, attempt = execute_transmission(uuid.UUID(transmission_id), uuid.UUID(tenant_id))
    if outcome == "retry":
        # max_retries generous on purpose: execute_transmission dead-letters by
        # itself once attempt_count reaches the configured maximum.
        raise self.retry(countdown=backoff_seconds(attempt), max_retries=10)
    return outcome


@celery_app.task(name="app.weekly_digest")
def weekly_digest() -> int:
    """FR-6.1 weekly digest: per-tenant 7-day status counts + penalty risk to the
    owners. Tenants are enumerated via the SECURITY DEFINER id-only function;
    all data access then runs under normal per-tenant RLS."""
    from datetime import date, timedelta

    from sqlalchemy import func as sa_func
    from sqlalchemy import select, text

    from app.models import Invoice
    from app.notifications.service import notify_owners
    from app.services.compliance_service import monthly_summary

    engine_session = get_sessionmaker()()
    try:
        tenant_ids = [row[0] for row in engine_session.execute(text("SELECT app_all_tenant_ids()"))]
    finally:
        engine_session.close()

    notified = 0
    week_ago = date.today() - timedelta(days=7)
    for tenant_id in tenant_ids:
        with tenant_session(tenant_id) as db:
            rows = db.execute(
                select(Invoice.status, sa_func.count())
                .where(Invoice.tenant_id == tenant_id, Invoice.issue_date >= week_ago)
                .group_by(Invoice.status)
            ).all()
            counts = {status: count for status, count in rows}
            summary = monthly_summary(db, tenant_id, None)
            notified += notify_owners(
                db,
                tenant_id,
                template="weekly_digest",
                params={
                    "accepted": counts.get("ACCEPTED", 0),
                    "rejected": counts.get("REJECTED", 0),
                    "drafts": counts.get("DRAFT", 0),
                    "penalty": summary["penalty_risk_aed"],
                },
            )
    return notified


@celery_app.task(name="app.register_participant")
def register_participant(tenant_id: str) -> str:
    from app.asp import get_asp_adapter

    tid = uuid.UUID(tenant_id)
    adapter = get_asp_adapter()
    with tenant_session(tid) as db:
        tenant = db.get(Tenant, tid)
        assert tenant is not None
        before = tenant.asp_onboarding_status
        registration = adapter.register_participant(trn=tenant.trn, legal_name=tenant.legal_name_en)
        tenant.asp_onboarding_status = registration.status
        tenant.asp_participant_id = registration.participant_id or None
        audit_service.record(
            db,
            tid,
            action="tenant.asp_onboarding",
            entity_type="tenant",
            entity_id=tid,
            actor_type="system",
            before={"status": before},
            after={
                "status": registration.status,
                "participant_id": registration.participant_id,
            },
        )
        return registration.status
