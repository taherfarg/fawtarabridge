import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict


class ArchiveRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    invoice_id: uuid.UUID
    invoice_number: str
    buyer_name: str
    buyer_trn: str | None
    issue_date: date
    total_including_vat: Decimal
    spec_version: str
    xml_hash: str
    retention_until: date
    ack: dict[str, Any]
    created_at: datetime


class ArchiveListOut(BaseModel):
    items: list[ArchiveRecordOut]
    total: int
    limit: int
    offset: int


class ComplianceSummaryOut(BaseModel):
    period: str
    total_invoices: int
    counts: dict[str, int]
    accepted_total_aed: Decimal
    unsent_past_due: int
    penalty_risk_aed: int
    penalty_cap_aed: int
    currency: str
