"""Tenant-scoped repository base: the query-layer half of tenant isolation.

RLS is the database-level guarantee; this layer makes it impossible to *write*
an unscoped query in application code in the first place. Every repository for a
tenant-owned table must inherit from TenantScopedRepository.
"""

import uuid
from typing import Any, ClassVar

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.db.base import Base


class TenantScopeError(RuntimeError):
    """Programming error: a tenant-scoped repository was used without/against scope."""


class TenantScopedRepository[ModelT: Base]:
    model: ClassVar[type]  # set by subclasses; must have a tenant_id column

    def __init__(self, session: Session, tenant_id: uuid.UUID) -> None:
        if not isinstance(tenant_id, uuid.UUID):
            raise TenantScopeError("tenant_id (UUID) is mandatory for tenant-scoped repositories")
        if not hasattr(self.model, "tenant_id"):
            raise TenantScopeError(f"{self.model.__name__} has no tenant_id column")
        self.session = session
        self.tenant_id = tenant_id

    def query(self) -> Select[tuple[ModelT]]:
        model: Any = self.model  # ClassVar[type] can't carry the column attributes
        stmt: Select[tuple[ModelT]] = select(model).where(model.tenant_id == self.tenant_id)
        return stmt

    def get(self, entity_id: uuid.UUID) -> ModelT | None:
        model: Any = self.model
        stmt = self.query().where(model.id == entity_id)
        return self.session.scalars(stmt).one_or_none()

    def list(self) -> list[ModelT]:
        return list(self.session.scalars(self.query()).all())

    def add(self, entity: ModelT) -> ModelT:
        current = getattr(entity, "tenant_id", None)
        if current is not None and current != self.tenant_id:
            raise TenantScopeError(
                f"attempt to persist {type(entity).__name__} for foreign tenant {current}"
            )
        entity.tenant_id = self.tenant_id  # type: ignore[attr-defined]
        self.session.add(entity)
        return entity
