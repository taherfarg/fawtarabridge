"""ASP status callbacks (FR-4.3): signed, idempotent, tenant context derived
from our own idempotency key — no RLS bypass needed."""

import uuid

from fastapi import APIRouter, Request
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy import select

from app.api.deps import DbDep
from app.asp.base import StatusResult
from app.asp.webhook import verify_signature
from app.config import get_settings
from app.core.errors import AppError
from app.db.session import set_rls_context
from app.models import Invoice, Transmission
from app.models.transmission import TRANSMISSION_TERMINAL_STATUSES
from app.schemas.transmission import WebhookAck, WebhookIn
from app.services.transmission_service import apply_asp_status

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/asp/{provider}", response_model=WebhookAck)
async def asp_status_callback(provider: str, request: Request, db: DbDep) -> WebhookAck:
    body = await request.body()
    signature = request.headers.get("X-ASP-Signature")
    if not verify_signature(get_settings().asp_webhook_secret, body, signature):
        raise AppError("webhook.invalid_signature", status_code=401)

    try:
        payload = WebhookIn.model_validate_json(body)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc

    # Key format "<tenant_id>:<invoice_id>:<hash>:<n>" — we minted it at queue time.
    try:
        tenant_id = uuid.UUID(payload.idempotency_key.split(":", 1)[0])
    except ValueError:
        raise AppError("webhook.unknown_message", status_code=404) from None

    set_rls_context(db, tenant_id=tenant_id)
    transmission = db.scalars(
        select(Transmission).where(Transmission.idempotency_key == payload.idempotency_key)
    ).one_or_none()
    if transmission is None or transmission.asp_provider != provider:
        raise AppError("webhook.unknown_message", status_code=404)
    if transmission.status in TRANSMISSION_TERMINAL_STATUSES:
        return WebhookAck(result="ignored")  # duplicate callback — idempotent

    invoice = db.get(Invoice, transmission.invoice_id)
    assert invoice is not None
    apply_asp_status(
        db,
        transmission,
        invoice,
        StatusResult(
            status=payload.status,
            rejection_code=payload.rejection_code,
            rejection_reason=payload.rejection_reason,
        ),
        actor_type="asp_webhook",
    )
    return WebhookAck(result="applied")
