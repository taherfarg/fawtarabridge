"""Test harness: disposable Postgres database, migrated via Alembic.

The app connects as ``fawtara_app`` (RLS applies); the harness uses the admin role
only to create/clean the test database. Override connection via TEST_DB_HOST /
TEST_DB_PORT / TEST_DB_ADMIN_USER / TEST_DB_ADMIN_PASSWORD (CI sets port 5432).
"""

import os
from collections.abc import Iterator
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]

DB_HOST = os.environ.get("TEST_DB_HOST", "localhost")
DB_PORT = os.environ.get("TEST_DB_PORT", "5433")
ADMIN_USER = os.environ.get("TEST_DB_ADMIN_USER", "fawtara")
ADMIN_PASSWORD = os.environ.get("TEST_DB_ADMIN_PASSWORD", "fawtara")
TEST_DB_NAME = "fawtara_test"

ADMIN_POSTGRES_URL = (
    f"postgresql+psycopg://{ADMIN_USER}:{ADMIN_PASSWORD}@{DB_HOST}:{DB_PORT}/postgres"
)
ADMIN_TEST_URL = (
    f"postgresql+psycopg://{ADMIN_USER}:{ADMIN_PASSWORD}@{DB_HOST}:{DB_PORT}/{TEST_DB_NAME}"
)
APP_TEST_URL = f"postgresql+psycopg://fawtara_app:fawtara_app@{DB_HOST}:{DB_PORT}/{TEST_DB_NAME}"

# Must happen before any `app.*` import (pytest imports conftest first).
os.environ["FAWTARA_DATABASE_URL"] = APP_TEST_URL
os.environ["FAWTARA_ADMIN_DATABASE_URL"] = ADMIN_TEST_URL

import uuid  # noqa: E402
from collections.abc import Callable  # noqa: E402

import pytest  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import Engine, create_engine, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from alembic import command  # noqa: E402
from app.db.session import get_sessionmaker, set_rls_context  # noqa: E402
from app.models import Tenant, TenantMembership, User  # noqa: E402
from app.models.enums import Role  # noqa: E402
from app.services.otp import get_otp_provider  # noqa: E402

SessionFactory = Callable[[], Session]

ALL_TABLES = (
    "import_mapping_templates, invoices, contacts, "
    "otp_codes, refresh_tokens, tenant_memberships, tenants, users"
)


@pytest.fixture(scope="session")
def database() -> Iterator[None]:
    admin = create_engine(ADMIN_POSTGRES_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB_NAME} WITH (FORCE)"))
        conn.execute(text(f"CREATE DATABASE {TEST_DB_NAME}"))
    admin.dispose()

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(scope="session")
def admin_engine(database: None) -> Iterator[Engine]:
    engine = create_engine(ADMIN_TEST_URL)
    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def clean_db(database: None, admin_engine: Engine) -> Iterator[None]:
    yield
    with admin_engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {ALL_TABLES} CASCADE"))


@pytest.fixture()
def client(database: None) -> Iterator[TestClient]:
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture()
def db_session(database: None) -> Iterator[Session]:
    """App-role session (RLS applies). GUCs are NOT set — tests set them explicitly."""
    session = get_sessionmaker()()
    yield session
    session.rollback()
    session.close()


@pytest.fixture()
def make_session(database: None) -> Iterator[SessionFactory]:
    """Factory for app-role sessions; all created sessions are closed on teardown."""
    sessions: list[Session] = []

    def factory() -> Session:
        s = get_sessionmaker()()
        sessions.append(s)
        return s

    yield factory
    for s in sessions:
        s.rollback()
        s.close()


def create_tenant_with_owner(
    factory: SessionFactory, *, trn: str, email: str
) -> tuple[uuid.UUID, uuid.UUID]:
    """Mimics signup at the ORM level: sets GUCs for the about-to-exist tenant/user,
    then inserts user + tenant + OWNER membership. Returns (tenant_id, user_id)."""
    session = factory()
    tenant_id, user_id = uuid.uuid4(), uuid.uuid4()
    set_rls_context(session, tenant_id=tenant_id, user_id=user_id)
    session.add_all(
        [
            User(
                id=user_id,
                email=email,
                password_hash="x",
                full_name="Owner",
                phone="+971501234567",
            ),
            Tenant(
                id=tenant_id,
                legal_name_ar="شركة",
                legal_name_en="Company",
                trn=trn,
            ),
        ]
    )
    # Parents must hit the DB before the membership row (no relationship() mappings).
    session.flush()
    session.add(TenantMembership(tenant_id=tenant_id, user_id=user_id, role=Role.OWNER))
    session.commit()
    session.close()
    return tenant_id, user_id


@pytest.fixture()
def two_tenants(
    make_session: SessionFactory,
) -> tuple[tuple[uuid.UUID, uuid.UUID], tuple[uuid.UUID, uuid.UUID]]:
    a = create_tenant_with_owner(make_session, trn="100000000000001", email="a@example.com")
    b = create_tenant_with_owner(make_session, trn="100000000000002", email="b@example.com")
    return a, b


class CapturingOTPProvider:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def send(self, phone: str, code: str) -> None:
        self.sent.append((phone, code))

    @property
    def last_code(self) -> str:
        return self.sent[-1][1]


@pytest.fixture()
def otp_outbox(client: TestClient) -> Iterator[CapturingOTPProvider]:
    from app.main import app

    provider = CapturingOTPProvider()
    app.dependency_overrides[get_otp_provider] = lambda: provider
    yield provider
    app.dependency_overrides.pop(get_otp_provider, None)


def signup_payload(
    email: str = "owner@example.com",
    trn: str = "100123456700001",
    phone: str = "+971501234567",
) -> dict:
    return {
        "email": email,
        "password": "Secret123!",
        "full_name": "Test Owner",
        "phone": phone,
        "company": {
            "legal_name_ar": "شركة الاختبار التجارية ذ.م.م",
            "legal_name_en": "Test Trading LLC",
            "trn": trn,
            "emirate": "Dubai",
            "revenue_band": "lt_50m",
        },
    }


def auth_headers(tokens: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}
