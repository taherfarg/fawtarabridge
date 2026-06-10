"""Engine/session factories and the RLS GUC context.

Request code uses the *app* engine (non-superuser role ``fawtara_app``); RLS
policies key on transaction-local GUCs set via :func:`set_rls_context`. The GUCs
are transaction-local (``set_config(..., is_local => true)``), so they vanish on
commit/rollback — a connection returned to the pool carries no tenant context.
"""

import uuid
from functools import lru_cache

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


@lru_cache
def get_engine() -> Engine:
    return create_engine(get_settings().database_url, pool_pre_ping=True)


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def set_rls_context(
    session: Session,
    *,
    tenant_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> None:
    """Set the RLS GUCs for the session's current transaction.

    Must be called after the transaction begins and again if the session
    commits mid-request (avoid mid-request commits for exactly this reason).
    """
    session.execute(
        text(
            "SELECT set_config('app.current_tenant_id', :tid, true),"
            "       set_config('app.current_user_id', :uid, true)"
        ),
        {
            "tid": str(tenant_id) if tenant_id else "",
            "uid": str(user_id) if user_id else "",
        },
    )
