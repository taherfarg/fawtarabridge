"""Invoice status lifecycle (architecture rule 7). Illegal transitions raise.

    DRAFT → VALIDATED → QUEUED → SENT → ACCEPTED | REJECTED | ERROR

Extensions beyond the happy path (documented in DECISIONS D-033):
- VALIDATED → DRAFT          editing / re-validation failure re-opens the draft
- REJECTED → DRAFT | QUEUED  fix-and-resend, or direct resend (transient ASP rejection)
- ERROR    → DRAFT | QUEUED  dead-letter replay after fixing / infra recovery
- ACCEPTED is terminal.

Every transition is recorded in the append-only audit log (who/what/when,
before/after) — use :func:`transition_invoice`, never set ``invoice.status``
directly outside this module.
"""

import enum
import uuid

from sqlalchemy.orm import Session

from app.models import Invoice
from app.services import audit_service


class InvoiceStatus(enum.StrEnum):
    DRAFT = "DRAFT"
    VALIDATED = "VALIDATED"
    QUEUED = "QUEUED"
    SENT = "SENT"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    ERROR = "ERROR"


ALLOWED_TRANSITIONS: dict[InvoiceStatus, frozenset[InvoiceStatus]] = {
    InvoiceStatus.DRAFT: frozenset({InvoiceStatus.VALIDATED}),
    InvoiceStatus.VALIDATED: frozenset({InvoiceStatus.DRAFT, InvoiceStatus.QUEUED}),
    InvoiceStatus.QUEUED: frozenset({InvoiceStatus.SENT, InvoiceStatus.ERROR}),
    InvoiceStatus.SENT: frozenset(
        {InvoiceStatus.ACCEPTED, InvoiceStatus.REJECTED, InvoiceStatus.ERROR}
    ),
    InvoiceStatus.ACCEPTED: frozenset(),  # terminal
    InvoiceStatus.REJECTED: frozenset({InvoiceStatus.DRAFT, InvoiceStatus.QUEUED}),
    InvoiceStatus.ERROR: frozenset({InvoiceStatus.DRAFT, InvoiceStatus.QUEUED}),
}


class IllegalTransitionError(Exception):
    def __init__(self, from_status: InvoiceStatus, to_status: InvoiceStatus) -> None:
        super().__init__(f"illegal invoice transition {from_status} -> {to_status}")
        self.from_status = from_status
        self.to_status = to_status


def assert_transition(from_status: InvoiceStatus, to_status: InvoiceStatus) -> None:
    if to_status not in ALLOWED_TRANSITIONS[from_status]:
        raise IllegalTransitionError(from_status, to_status)


def transition_invoice(
    db: Session,
    invoice: Invoice,
    to_status: InvoiceStatus,
    *,
    actor_id: uuid.UUID | None,
    actor_type: str = "user",
    extra: dict | None = None,
) -> None:
    from_status = InvoiceStatus(invoice.status)
    assert_transition(from_status, to_status)
    invoice.status = to_status.value
    audit_service.record(
        db,
        invoice.tenant_id,
        action="invoice.status_changed",
        entity_type="invoice",
        entity_id=invoice.id,
        actor_id=actor_id,
        actor_type=actor_type,
        before={"status": from_status.value},
        after={"status": to_status.value, **(extra or {})},
    )
