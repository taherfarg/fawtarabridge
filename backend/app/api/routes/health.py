from fastapi import APIRouter, Response
from sqlalchemy import text

from app.db.session import get_sessionmaker

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness — process is up."""
    return {"status": "ok"}


@router.get("/health/ready")
def readiness(response: Response) -> dict[str, str]:
    """Readiness — dependencies reachable (DB; Redis is fail-open by design)."""
    checks: dict[str, str] = {}
    try:
        session = get_sessionmaker()()
        try:
            session.execute(text("SELECT 1"))
            checks["database"] = "ok"
        finally:
            session.close()
    except Exception:
        checks["database"] = "down"
        response.status_code = 503
    checks["status"] = "ok" if checks["database"] == "ok" else "degraded"
    return checks
