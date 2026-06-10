from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import register_exception_handlers
from app.api.routes import auth, health, tenants, users
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
    app.include_router(api_v1)
    app.include_router(health.router)

    register_exception_handlers(app)
    return app


app = create_app()
