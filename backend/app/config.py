from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FAWTARA_", env_file=".env", extra="ignore")

    env: str = "dev"

    # Runtime connection: non-superuser role, RLS applies.
    database_url: str = "postgresql+psycopg://fawtara_app:fawtara_app@localhost:5433/fawtara"
    # Owner/admin connection: migrations and test harness only. Never used by request code.
    admin_database_url: str = "postgresql+psycopg://fawtara:fawtara@localhost:5433/fawtara"

    redis_url: str = "redis://localhost:6380/0"

    # ≥ 32 bytes for HS256 (RFC 7518); production injects its own via env/vault
    jwt_secret: str = "dev-only-secret-change-me-0123456789abcdef"
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 30

    otp_ttl_minutes: int = 10
    otp_max_attempts: int = 5

    default_locale: str = "ar"

    # SPEC-CHECK: align with the official MoF spec version identifier once published.
    pintae_default_spec_version: str = "pint-ae-1.0"

    asp_provider: str = "mock"
    asp_webhook_secret: str = "dev-webhook-secret-change-me-0123456789"
    transmission_max_attempts: int = 5
    transmission_backoff_base_seconds: int = 30

    celery_eager: bool = False  # tests run tasks inline

    # Penalty model (build instructions; SPEC-CHECK against Cabinet Res. 106/2025)
    penalty_per_unsent_invoice_aed: int = 100
    penalty_monthly_cap_aed: int = 5000
    reporting_grace_days: int = 2

    cors_origins: list[str] = ["http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
