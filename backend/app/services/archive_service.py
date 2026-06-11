"""Immutable archive creation + retention (FR-7.1). Records are written exactly
once, when an invoice reaches ACCEPTED, inside the same transaction as the
status transition — a cleared invoice is never observable without its archive."""

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import sha256_hex
from app.models import Invoice, Transmission
from app.models.archive import ArchiveRecord
from app.pintae import get_engine
from app.services import audit_service, invoice_service, pdf_service

RETENTION_YEARS = 5


def retention_until(issue_date: date) -> date:
    """issue_date + 5 years (build instruction).

    # SPEC-CHECK: FTA retention may count from the end of the relevant tax
    # period rather than the issue date — confirm and adjust if needed.
    """
    try:
        return issue_date.replace(year=issue_date.year + RETENTION_YEARS)
    except ValueError:  # Feb 29 -> Feb 28 of the non-leap target year
        return issue_date.replace(year=issue_date.year + RETENTION_YEARS, day=28)


def create_archive(
    db: Session, invoice: Invoice, transmission: Transmission | None, ack: dict[str, Any]
) -> ArchiveRecord | None:
    """Idempotent: an existing archive for the invoice wins (re-delivered events)."""
    existing = db.scalars(
        select(ArchiveRecord).where(ArchiveRecord.invoice_id == invoice.id)
    ).one_or_none()
    if existing is not None:
        return None

    canonical = invoice_service.rehydrate(invoice)
    engine = get_engine(invoice.spec_version)
    generated = engine.generate(canonical)
    xml_hash = sha256_hex(generated.xml.decode("utf-8"))
    pdf = pdf_service.render_invoice_pdf(
        canonical,
        status=invoice.status,
        spec_version=generated.spec_version,
        xml_hash=xml_hash,
    )

    record = ArchiveRecord(
        tenant_id=invoice.tenant_id,
        invoice_id=invoice.id,
        transmission_id=transmission.id if transmission is not None else None,
        invoice_number=invoice.invoice_number,
        buyer_name=invoice.buyer_name,
        buyer_trn=invoice.buyer_trn,
        issue_date=invoice.issue_date,
        total_including_vat=invoice.total_including_vat,
        spec_version=generated.spec_version,
        xml=generated.xml,
        pdf=pdf,
        ack=ack,
        xml_hash=xml_hash,
        retention_until=retention_until(invoice.issue_date),
    )
    db.add(record)
    db.flush()
    audit_service.record(
        db,
        invoice.tenant_id,
        action="invoice.archived",
        entity_type="invoice",
        entity_id=invoice.id,
        actor_type="system",
        after={"archive_id": str(record.id), "retention_until": record.retention_until.isoformat()},
    )
    return record
