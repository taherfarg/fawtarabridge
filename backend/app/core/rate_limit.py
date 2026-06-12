"""Fixed-window rate limiting for auth endpoints (NFR: brute-force protection).

Redis INCR + EXPIRE per (client IP, route, minute). Fail-open: if Redis is
down, auth still works — availability of login beats throttling fidelity.
"""

import logging
import time
from functools import lru_cache

from fastapi import Request
from redis import Redis

from app.config import get_settings
from app.core.errors import AppError

logger = logging.getLogger(__name__)


@lru_cache
def _redis() -> Redis:
    return Redis.from_url(get_settings().redis_url, socket_timeout=1)


def enforce_auth_rate_limit(request: Request) -> None:
    settings = get_settings()
    if not settings.auth_rate_limit_enabled:
        return
    client_ip = request.client.host if request.client else "unknown"
    window = int(time.time() // 60)
    key = f"ratelimit:auth:{client_ip}:{request.url.path}:{window}"
    try:
        client = _redis()
        count = client.incr(key)
        if count == 1:
            client.expire(key, 90)
    except Exception:  # pragma: no cover — fail-open by design
        logger.warning("rate limiter unavailable; allowing request")
        return
    if int(count) > settings.auth_rate_limit_per_minute:
        raise AppError("auth.rate_limited", status_code=429)
