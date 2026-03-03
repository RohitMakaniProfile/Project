"""Rate limiting middleware using Redis sliding window."""
import time
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.redis_client import get_redis
from app.config import get_settings
from app.logging_config import get_logger

logger = get_logger(__name__)

# Paths that should be rate-limited (product endpoints)
RATE_LIMITED_PREFIXES = ("/api/",)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Per-organisation rate limiting using a Redis sliding window counter.
    Maximum 60 requests per minute per organisation across all product endpoints.

    If Redis is unavailable, the system fails open (allows all requests).
    This is a deliberate decision documented in DECISIONS.md.
    """

    async def dispatch(self, request: Request, call_next):
        # Only rate-limit product endpoints
        if not any(request.url.path.startswith(p) for p in RATE_LIMITED_PREFIXES):
            return await call_next(request)

        # Try to extract org_id from JWT (without full validation — just for rate limiting key)
        org_id = await self._extract_org_id(request)
        if org_id is None:
            # No org_id means no auth — let the auth middleware handle the 401
            return await call_next(request)

        redis = await get_redis()
        if redis is None:
            # Redis unavailable — fail open
            logger.warning("rate_limit_redis_unavailable", path=request.url.path)
            return await call_next(request)

        settings = get_settings()
        key = f"ratelimit:{org_id}"
        window = 60  # 1 minute
        limit = settings.RATE_LIMIT_PER_MINUTE

        try:
            now = time.time()
            pipe = redis.pipeline()
            # Remove expired entries
            pipe.zremrangebyscore(key, 0, now - window)
            # Count current requests in window
            pipe.zcard(key)
            # Add current request
            pipe.zadd(key, {f"{now}:{id(request)}": now})
            # Set key expiry
            pipe.expire(key, window)
            results = await pipe.execute()

            current_count = results[1]

            if current_count >= limit:
                # Calculate retry-after
                oldest = await redis.zrange(key, 0, 0, withscores=True)
                if oldest:
                    retry_after = int(window - (now - oldest[0][1])) + 1
                else:
                    retry_after = window

                logger.warning(
                    "rate_limit_exceeded",
                    org_id=org_id,
                    count=current_count,
                    limit=limit,
                )
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    headers={"Retry-After": str(retry_after)},
                    content={
                        "error": "rate_limit_exceeded",
                        "message": f"Rate limit of {limit} requests per minute exceeded.",
                        "request_id": str(getattr(request.state, "request_id", "unknown")),
                    },
                )

        except Exception as e:
            # Redis error — fail open
            logger.warning("rate_limit_error", error=str(e))

        return await call_next(request)

    async def _extract_org_id(self, request: Request) -> str | None:
        """Extract org_id from the Authorization header JWT without full validation."""
        from jose import jwt, JWTError
        from app.config import get_settings

        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            return None

        token = auth_header[7:]
        try:
            settings = get_settings()
            payload = jwt.decode(
                token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
            )
            return payload.get("org_id")
        except JWTError:
            return None
