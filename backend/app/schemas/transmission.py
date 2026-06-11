import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from app.asp.rejections import rejection_detail
from app.core.errors import ErrorDetail
from app.models import Transmission


class TransmissionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    invoice_id: uuid.UUID
    status: str
    attempt_count: int
    asp_provider: str
    asp_message_id: str | None
    spec_version: str
    last_error: str | None
    rejection_code: str | None
    rejection: ErrorDetail | None = None  # bilingual, derived from rejection_code
    created_at: datetime
    completed_at: datetime | None

    @classmethod
    def from_model(cls, transmission: Transmission) -> "TransmissionOut":
        out = cls.model_validate(transmission)
        if transmission.status == "rejected":
            out.rejection = rejection_detail(
                transmission.rejection_code, transmission.rejection_reason
            )
        return out


class SendOut(BaseModel):
    invoice_id: uuid.UUID
    invoice_status: str
    transmission: TransmissionOut


class AuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    action: str
    entity_type: str
    entity_id: uuid.UUID
    actor_id: uuid.UUID | None
    actor_type: str
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    created_at: datetime


class WebhookIn(BaseModel):
    idempotency_key: str
    message_id: str | None = None
    status: Literal["accepted", "rejected", "error"]
    rejection_code: str | None = None
    rejection_reason: str | None = None


class WebhookAck(BaseModel):
    result: Literal["applied", "ignored"]
