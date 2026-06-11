"""Append-only audit recording. INSERT-only by DB grants — there is no update/delete
code path here on purpose, and none would work (migration 0003 withholds the
privileges from the app role)."""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit import AuditEvent


def record(
    db: Session,
    tenant_id: uuid.UUID,
    *,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID,
    actor_id: uuid.UUID | None = None,
    actor_type: str = "user",
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> AuditEvent:
    event = AuditEvent(
        tenant_id=tenant_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_id=actor_id,
        actor_type=actor_type,
        before=before,
        after=after,
    )
    db.add(event)
    return event


def list_for_entity(
    db: Session, tenant_id: uuid.UUID, *, entity_type: str, entity_id: uuid.UUID
) -> list[AuditEvent]:
    stmt = (
        select(AuditEvent)
        .where(
            AuditEvent.tenant_id == tenant_id,
            AuditEvent.entity_type == entity_type,
            AuditEvent.entity_id == entity_id,
        )
        .order_by(AuditEvent.created_at, AuditEvent.id)
    )
    return list(db.scalars(stmt).all())
