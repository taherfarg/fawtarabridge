import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.errors import ErrorDetail
from app.pintae.canonical import VatCategory


class ColumnMapping(BaseModel):
    """File-column name per canonical field. Required fields must always be mapped;
    optional ones may be omitted when the file has no such column."""

    invoice_number: str
    issue_date: str
    buyer_name: str
    description: str
    quantity: str
    unit_price: str
    vat_treatment: str
    buyer_trn: str | None = None
    discount_amount: str | None = None
    exemption_reason: str | None = None
    due_date: str | None = None
    note: str | None = None
    line_net: str | None = None
    line_vat: str | None = None
    total_excluding_vat: str | None = None
    total_vat: str | None = None
    total_including_vat: str | None = None


class ImportMapping(BaseModel):
    columns: ColumnMapping
    # Maps raw VAT cell values to categories, e.g. {"5%": "S", "exempt": "E"}.
    # Matching is case-insensitive and trimmed; bare category codes always work.
    vat_value_map: dict[str, VatCategory] = Field(default_factory=dict)
    date_format: str = "%Y-%m-%d"

    @field_validator("vat_value_map", mode="before")
    @classmethod
    def normalize_keys(cls, v: dict[str, Any]) -> dict[str, Any]:
        return {str(k).strip().lower(): val for k, val in v.items()}


class ImportRequestMeta(BaseModel):
    mapping: ImportMapping | None = None
    template_id: uuid.UUID | None = None
    save_template_name: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def mapping_or_template(self) -> "ImportRequestMeta":
        if self.mapping is None and self.template_id is None:
            raise ValueError("either mapping or template_id is required")
        return self


class RowIssue(BaseModel):
    row: int  # 1-based data-row number as the customer sees it in their file
    errors: list[ErrorDetail]


class ImportInvoiceReport(BaseModel):
    invoice_number: str
    rows: list[int]
    valid: bool
    errors: list[ErrorDetail]
    warnings: list[ErrorDetail]
    invoice_id: uuid.UUID | None = None  # set on commit


class ImportSummary(BaseModel):
    rows: int
    invoices: int
    valid: int
    invalid: int
    created: int = 0


class ImportReportOut(BaseModel):
    summary: ImportSummary
    file_errors: list[ErrorDetail]
    row_issues: list[RowIssue]
    invoices: list[ImportInvoiceReport]
    saved_template_id: uuid.UUID | None = None


class MappingTemplateIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    mapping: ImportMapping


class MappingTemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    mapping: ImportMapping
