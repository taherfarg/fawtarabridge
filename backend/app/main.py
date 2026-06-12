from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import register_exception_handlers
from app.api.routes import (
    archive,
    auth,
    billing,
    compliance,
    contacts,
    health,
    imports,
    invoices,
    tenants,
    transmissions,
    users,
    webhooks,
)
from app.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="FawtaraBridge API",
        version="0.1.0",
        description="UAE e-invoicing compliance platform — PINT-AE generation & ASP transmission",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    api_v1 = APIRouter(prefix="/api/v1")
    api_v1.include_router(auth.router)
    api_v1.include_router(tenants.router)
    api_v1.include_router(users.router)
    api_v1.include_router(contacts.router)
    api_v1.include_router(invoices.router)
    api_v1.include_router(imports.router)
    api_v1.include_router(transmissions.router)
    api_v1.include_router(webhooks.router)
    api_v1.include_router(archive.router)
    api_v1.include_router(compliance.router)
    api_v1.include_router(billing.router)
    app.include_router(api_v1)
    app.include_router(health.router)

    register_exception_handlers(app)
    return app


app = create_app()
