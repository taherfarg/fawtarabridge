import csv
import io
import uuid
import zipfile
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.api.deps import AuthContext, AuthDep, TenantDbDep, require_roles
from app.core.errors import AppError
from app.models.archive import ArchiveRecord
from app.models.enums import Role
from app.repositories.archive import ArchiveRepository
from app.schemas.archive import ArchiveListOut, ArchiveRecordOut

router = APIRouter(prefix="/archive", tags=["archive"])

ExportCtx = Annotated[AuthContext, Depends(require_roles(Role.OWNER, Role.ACCOUNTANT))]


def _get_or_404(repo: ArchiveRepository, archive_id: uuid.UUID) -> ArchiveRecord:
    record = repo.get(archive_id)
    if record is None:
        raise AppError("archive.not_found", status_code=404)
    return record


@router.get("", response_model=ArchiveListOut)
def search_archive(
    db: TenantDbDep,
    ctx: AuthDep,
    search: str | None = Query(default=None, max_length=100),
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ArchiveListOut:
    items, total = ArchiveRepository(db, ctx.tenant_id).search(
        query=search, date_from=date_from, date_to=date_to, limit=limit, offset=offset
    )
    return ArchiveListOut(
        items=[ArchiveRecordOut.model_validate(r) for r in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/export")
def export_archive_zip(
    db: TenantDbDep,
    ctx: ExportCtx,
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
) -> Response:
    """One-click FTA audit export (FR-7.3): XML + PDF per invoice + index.csv."""
    records = ArchiveRepository(db, ctx.tenant_id).for_export(date_from=date_from, date_to=date_to)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as bundle:
        index = io.StringIO()
        writer = csv.writer(index)
        writer.writerow(
            [
                "invoice_number",
                "issue_date",
                "buyer_name",
                "buyer_trn",
                "total_including_vat",
                "spec_version",
                "xml_hash",
                "retention_until",
            ]
        )
        for record in records:
            safe = record.invoice_number.replace("/", "_")
            bundle.writestr(f"{safe}.xml", record.xml)
            bundle.writestr(f"{safe}.pdf", record.pdf)
            writer.writerow(
                [
                    record.invoice_number,
                    record.issue_date.isoformat(),
                    record.buyer_name,
                    record.buyer_trn or "",
                    str(record.total_including_vat),
                    record.spec_version,
                    record.xml_hash,
                    record.retention_until.isoformat(),
                ]
            )
        bundle.writestr("index.csv", index.getvalue())

    name_from = date_from.isoformat() if date_from else "all"
    name_to = date_to.isoformat() if date_to else "all"
    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="archive-{name_from}-{name_to}.zip"'
        },
    )


@router.get("/{archive_id}/xml")
def download_archived_xml(archive_id: uuid.UUID, db: TenantDbDep, ctx: AuthDep) -> Response:
    record = _get_or_404(ArchiveRepository(db, ctx.tenant_id), archive_id)
    return Response(
        content=record.xml,
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{record.invoice_number}.xml"'},
    )


@router.get("/{archive_id}/pdf")
def download_archived_pdf(archive_id: uuid.UUID, db: TenantDbDep, ctx: AuthDep) -> Response:
    record = _get_or_404(ArchiveRepository(db, ctx.tenant_id), archive_id)
    return Response(
        content=record.pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{record.invoice_number}.pdf"'},
    )
