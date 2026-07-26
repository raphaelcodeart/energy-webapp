"""IP-based rate limiting for abuse-prone public endpoints (login, register,
password reset request/confirm). Fixed-window counter in Redis -- already a
running dependency (celery's broker), just not previously used directly by
the API process. Fails open (allows the request) if Redis is unreachable:
an outage of the rate limiter must never take down login/registration
entirely, and Redis is not in this app's data-durability path."""

import redis.asyncio as redis
from fastapi import HTTPException, Request, status

from app.core.config import get_settings

settings = get_settings()
_redis_client: redis.Redis | None = None


def _get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client


def _client_ip(request: Request) -> str:
    # Uvicorn is started with --proxy-headers --forwarded-allow-ips, so
    # request.client.host already reflects X-Forwarded-For from nginx (see
    # docker-compose.dev.yml) rather than nginx's own container IP -- this is
    # just a defensive fallback in case that ever regresses.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(key_prefix: str, *, max_requests: int, window_seconds: int):
    """FastAPI dependency factory: `Depends(rate_limit("login", max_requests=10,
    window_seconds=60))`. One counter per (key_prefix, client IP), not per
    account -- this is the outer defense against distributed credential
    stuffing / registration spam; per-account lockout (User.locked_until) is
    the separate, existing inner defense against a single targeted account."""

    async def _checker(request: Request) -> None:
        client = _get_redis()
        redis_key = f"ratelimit:{key_prefix}:{_client_ip(request)}"
        try:
            count = await client.incr(redis_key)
            if count == 1:
                await client.expire(redis_key, window_seconds)
        except redis.RedisError:
            return  # fail open -- see module docstring
        if count > max_requests:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Troppi tentativi. Riprova tra qualche minuto.",
            )

    return _checker
