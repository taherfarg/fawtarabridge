"""Queue + execute invoice transmissions (architecture rule 4).

The API only ever creates a Transmission row and enqueues the Celery task —
it never talks to the ASP. The task body lives here as `execute_transmission`
(pure function of ids) so retry/dead-letter behavior is unit-testable without a
broker; the Celery wrapper in app.worker.tasks adds backoff scheduling.
"""

import uuid
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.asp import ASPTransientError, StatusResult, get_asp_adapter
from app.config import get_settings
from app.core.errors import AppError
from app.core.security import sha256_hex
from app.db.session import tenant_session
from app.lifecycle.state_machine import InvoiceStatus, transition_invoice
from app.models import Invoice, Transmission
from app.models.transmission import TRANSMISSION_TERMINAL_STATUSES
from app.pintae import get_engine
from app.services import audit_service, invoice_service

SENDABLE = frozenset({InvoiceStatus.VALIDATED})
RESENDABLE = frozenset({InvoiceStatus.REJECTED, InvoiceStatus.ERROR})


def queue_transmission(
    db: Session, invoice: Invoice, *, actor_id: uuid.UUID, resend: bool = False
) -> Transmission:
    """Create the transmission row and move the invoice to QUEUED.

    Raises InvoiceValidationError if the content no longer passes the engine —
    nothing invalid is ever queued, even on direct resend.
    """
    status = InvoiceStatus(invoice.status)
    if not resend and status not in SENDABLE:
        raise AppError("invoice.not_sendable", status_code=409, params={"status": status.value})
    if resend and status not in RESENDABLE:
        raise AppError("invoice.not_resendable", status_code=409, params={"status": status.value})

    engine = get_engine(invoice.spec_version)
    generated = engine.generate(invoice_service.rehydrate(invoice))  # may raise
    xml_hash = sha256_hex(generated.xml.decode("utf-8"))

    ordinal = (
        db.scalar(
            select(func.count())
            .select_from(Transmission)
            .where(Transmission.invoice_id == invoice.id)
        )
        or 0
    ) + 1
    transmission = Transmission(
        tenant_id=invoice.tenant_id,
        invoice_id=invoice.id,
        idempotency_key=(f"{invoice.tenant_id}:{invoice.id}:{xml_hash[:16]}:{ordinal}"),
        asp_provider=get_settings().asp_provider,
        spec_version=generated.spec_version,
        xml_hash=xml_hash,
    )
    db.add(transmission)
    db.flush()

    # Metering (FR-8.2): first send of an invoice counts, resends are free.
    # Never blocks — billing problems must not stop compliance transmissions.
    from app.billing.service import record_transmission_usage
    from app.models import Tenant

    tenant = db.get(Tenant, invoice.tenant_id)
    if tenant is not None:
        record_transmission_usage(db, tenant, first_send=ordinal == 1)

    transition_invoice(
        db,
        invoice,
        InvoiceStatus.QUEUED,
        actor_id=actor_id,
        extra={"transmission_id": str(transmission.id), "resend": resend},
    )
    return transmission


def apply_asp_status(
    db: Session,
    transmission: Transmission,
    invoice: Invoice,
    status: StatusResult,
    *,
    actor_type: str,
) -> None:
    """Shared by the worker (status poll) and the webhook endpoint."""
    if status.status == "processing":
        return
    now = datetime.now(UTC)
    if status.status == "accepted":
        transmission.status = "accepted"
        transmission.completed_at = now
        transition_invoice(
            db, invoice, InvoiceStatus.ACCEPTED, actor_id=None, actor_type=actor_type
        )
        # Same transaction as the transition: a cleared invoice is never
        # observable without its immutable archive (FR-7.1).
        from app.services import archive_service

        archive_service.create_archive(
            db,
            invoice,
            transmission,
            ack={
                "provider": transmission.asp_provider,
                "message_id": transmission.asp_message_id,
                "status": "accepted",
                "source": actor_type,
                "received_at": now.isoformat(),
            },
        )
    elif status.status == "rejected":
        transmission.status = "rejected"
        transmission.rejection_code = status.rejection_code
        transmission.rejection_reason = status.rejection_reason
        transmission.completed_at = now
        transition_invoice(
            db,
            invoice,
            InvoiceStatus.REJECTED,
            actor_id=None,
            actor_type=actor_type,
            extra={"rejection_code": status.rejection_code or ""},
        )
        # FR-6.1: rejection alerts to owners (cannot be disabled — FR-6.3).
        from app.notifications.service import notify_owners

        notify_owners(
            db,
            invoice.tenant_id,
            template="invoice_rejected",
            params={
                "number": invoice.invoice_number,
                "code": status.rejection_code or "?",
            },
        )
    else:  # "error"
        transmission.status = "failed"
        transmission.last_error = status.rejection_reason or "ASP reported an error"
        transmission.completed_at = now
        transition_invoice(db, invoice, InvoiceStatus.ERROR, actor_id=None, actor_type=actor_type)


def execute_transmission(
    transmission_id: uuid.UUID, tenant_id: uuid.UUID
) -> tuple[Literal["done", "retry"], int]:
    """One delivery attempt. Returns ("retry", attempt) when the Celery wrapper
    should back off and try again; everything else is finalized here."""
    settings = get_settings()
    adapter = get_asp_adapter()

    with tenant_session(tenant_id) as db:
        transmission = db.get(Transmission, transmission_id)
        if transmission is None or transmission.status in TRANSMISSION_TERMINAL_STATUSES:
            # Duplicate task delivery (at-least-once semantics): nothing to do.
            return ("done", transmission.attempt_count if transmission else 0)
        invoice = db.get(Invoice, transmission.invoice_id)
        assert invoice is not None  # FK

        transmission.attempt_count += 1
        attempt = transmission.attempt_count
        audit_service.record(
            db,
            tenant_id,
            action="transmission.attempt",
            entity_type="transmission",
            entity_id=transmission.id,
            actor_type="system",
            after={"attempt": attempt, "invoice_id": str(invoice.id)},
        )

        canonical = invoice_service.rehydrate(invoice)
        try:
            engine = get_engine(transmission.spec_version)
            xml = engine.generate(canonical).xml
            result = adapter.send_invoice(
                xml,
                idempotency_key=transmission.idempotency_key,
                sender_trn=canonical.supplier.trn or "",
                receiver_trn=canonical.buyer.trn,
            )
        except ASPTransientError as exc:
            transmission.last_error = str(exc)
            if attempt >= settings.transmission_max_attempts:
                transmission.status = "dead_letter"
                transmission.completed_at = datetime.now(UTC)
                audit_service.record(
                    db,
                    tenant_id,
                    action="transmission.dead_letter",
                    entity_type="transmission",
                    entity_id=transmission.id,
                    actor_type="system",
                    after={"attempts": attempt, "error": str(exc)},
                )
                transition_invoice(
                    db,
                    invoice,
                    InvoiceStatus.ERROR,
                    actor_id=None,
                    actor_type="system",
                    extra={"reason": "dead_letter"},
                )
                return ("done", attempt)
            return ("retry", attempt)
        except Exception as exc:  # ASPPermanentError, InvoiceValidationError, bugs
            transmission.status = "failed"
            transmission.last_error = str(exc)
            transmission.completed_at = datetime.now(UTC)
            transition_invoice(
                db,
                invoice,
                InvoiceStatus.ERROR,
                actor_id=None,
                actor_type="system",
                extra={"reason": "permanent_failure"},
            )
            return ("done", attempt)

        transmission.asp_message_id = result.message_id
        transmission.status = "sent"
        transition_invoice(
            db,
            invoice,
            InvoiceStatus.SENT,
            actor_id=None,
            actor_type="system",
            extra={"asp_message_id": result.message_id},
        )

        status = adapter.get_status(result.message_id)
        apply_asp_status(db, transmission, invoice, status, actor_type="system")
        return ("done", attempt)


def backoff_seconds(attempt: int) -> int:
    """Exponential backoff: base * 2^(attempt-1), capped at 30 minutes."""
    base = get_settings().transmission_backoff_base_seconds
    return min(base * 2 ** max(attempt - 1, 0), 1800)
