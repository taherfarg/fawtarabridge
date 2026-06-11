"""CSV/Excel import orchestration: preview and commit share one code path."""

import uuid

from sqlalchemy.orm import Session

from app.core.errors import AppError, ErrorDetail
from app.intake.importer import (
    ImportFileError,
    InvoiceGroup,
    check_columns,
    group_rows,
    parse_file,
)
from app.models import Tenant
from app.pintae import CanonicalInvoice, get_engine
from app.pintae.canonical import InvoiceLine, Party
from app.repositories.invoices import InvoiceRepository
from app.repositories.templates import MappingTemplateRepository
from app.schemas.importing import (
    ImportInvoiceReport,
    ImportMapping,
    ImportReportOut,
    ImportRequestMeta,
    ImportSummary,
    RowIssue,
)
from app.services import invoice_service


def _resolve_mapping(
    templates: MappingTemplateRepository, meta: ImportRequestMeta
) -> ImportMapping:
    if meta.mapping is not None:
        return meta.mapping
    assert meta.template_id is not None  # schema guarantees one of the two
    template = templates.get(meta.template_id)
    if template is None:
        raise AppError("import.template_not_found", status_code=404)
    return ImportMapping.model_validate(template.mapping)


def _build_canonical(tenant: Tenant, group: InvoiceGroup) -> CanonicalInvoice:
    header = group.header
    lines = [
        InvoiceLine(line_id=str(index + 1), **line.values) for index, line in enumerate(group.lines)
    ]
    return CanonicalInvoice(
        invoice_number=group.invoice_number,
        issue_date=header["issue_date"],
        due_date=header.get("due_date"),
        note=header.get("note"),
        supplier=invoice_service.supplier_party(tenant),
        buyer=Party(name=header.get("buyer_name", ""), trn=header.get("buyer_trn")),
        lines=lines,
        declared_total_excluding_vat=header.get("total_excluding_vat"),
        declared_total_vat=header.get("total_vat"),
        declared_total_including_vat=header.get("total_including_vat"),
    )


def run_import(
    db: Session,
    tenant: Tenant,
    *,
    user_id: uuid.UUID,
    filename: str,
    content: bytes,
    meta: ImportRequestMeta,
    persist: bool,
) -> ImportReportOut:
    templates = MappingTemplateRepository(db, tenant.id)
    invoices_repo = InvoiceRepository(db, tenant.id)
    mapping = _resolve_mapping(templates, meta)
    engine = get_engine()

    try:
        parsed = parse_file(filename, content)
    except ImportFileError as exc:
        return ImportReportOut(
            summary=ImportSummary(rows=0, invoices=0, valid=0, invalid=0),
            file_errors=exc.errors,
            row_issues=[],
            invoices=[],
        )

    column_errors = check_columns(parsed, mapping)
    if column_errors:
        return ImportReportOut(
            summary=ImportSummary(rows=len(parsed.rows), invoices=0, valid=0, invalid=0),
            file_errors=column_errors,
            row_issues=[],
            invoices=[],
        )

    groups, orphan_issues = group_rows(parsed, mapping)
    reports: list[ImportInvoiceReport] = []
    created = 0

    for group in groups:
        errors: list[ErrorDetail] = list(group.errors)
        warnings: list[ErrorDetail] = []
        canonical: CanonicalInvoice | None = None

        if not errors:
            canonical = _build_canonical(tenant, group)
            errors.extend(engine.validate(canonical))
            _, warnings = invoice_service.duplicate_warnings(invoices_repo, canonical)

        report = ImportInvoiceReport(
            invoice_number=group.invoice_number,
            rows=group.rows,
            valid=not errors,
            errors=errors,
            warnings=warnings,
        )

        if persist and report.valid and canonical is not None:
            try:
                # SAVEPOINT per invoice: a constraint violation (e.g. duplicate
                # number) must not abort the transaction for the rest of the batch.
                with db.begin_nested():
                    invoice, _, _ = invoice_service.create_invoice(
                        db,
                        invoices_repo,
                        tenant,
                        canonical,
                        contact_id=None,
                        created_by=user_id,
                    )
            except AppError as exc:  # e.g. invoice number already exists
                report.valid = False
                report.errors = [exc.detail()]
            else:
                report.invoice_id = invoice.id
                created += 1

        reports.append(report)

    saved_template_id: uuid.UUID | None = None
    if meta.save_template_name:
        existing = templates.get_by_name(meta.save_template_name)
        if existing is None:
            from app.models import ImportMappingTemplate

            template = templates.add(
                ImportMappingTemplate(
                    name=meta.save_template_name,
                    mapping=mapping.model_dump(mode="json"),
                )
            )
            db.flush()
            saved_template_id = template.id
        else:  # saving under an existing name updates it (wizard "save mapping" UX)
            existing.mapping = mapping.model_dump(mode="json")
            saved_template_id = existing.id

    valid_count = sum(1 for r in reports if r.valid)
    return ImportReportOut(
        summary=ImportSummary(
            rows=len(parsed.rows),
            invoices=len(reports),
            valid=valid_count,
            invalid=len(reports) - valid_count,
            created=created,
        ),
        file_errors=[],
        row_issues=[RowIssue(row=row, errors=errs) for row, errs in orphan_issues],
        invoices=reports,
        saved_template_id=saved_template_id,
    )
