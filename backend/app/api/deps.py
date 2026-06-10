import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.security import decode_token
from app.db.session import get_sessionmaker, set_rls_context
from app.models.enums import Role

_bearer = HTTPBearer(auto_error=False)


def get_db() -> Iterator[Session]:
    """One session + one transaction per request; commit on success."""
    session = get_sessionmaker()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@dataclass(frozen=True)
class AuthContext:
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    role: Role


def get_auth_context(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> AuthContext:
    if creds is None:
        raise AppError("auth.not_authenticated", status_code=401)
    payload = decode_token(creds.credentials, expected_type="access")
    return AuthContext(
        user_id=uuid.UUID(payload["sub"]),
        tenant_id=uuid.UUID(payload["tid"]),
        role=Role(payload["role"]),
    )


DbDep = Annotated[Session, Depends(get_db)]
AuthDep = Annotated[AuthContext, Depends(get_auth_context)]


def get_tenant_db(db: DbDep, ctx: AuthDep) -> Session:
    """Session with RLS GUCs bound to the authenticated tenant + user."""
    set_rls_context(db, tenant_id=ctx.tenant_id, user_id=ctx.user_id)
    return db


TenantDbDep = Annotated[Session, Depends(get_tenant_db)]


def require_roles(*roles: Role) -> Callable[[AuthContext], AuthContext]:
    def dependency(ctx: AuthDep) -> AuthContext:
        if ctx.role not in roles:
            raise AppError("auth.forbidden", status_code=403)
        return ctx

    return dependency
