"""Celery tasks. Logic lives in services; tasks only add queue semantics."""

import uuid

from app.db.session import tenant_session
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
