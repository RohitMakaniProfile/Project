"""Request logging middleware — structured JSON logging for every request."""
import time
import uuid as _uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.logging_config import get_logger

logger = get_logger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Logs every request with: timestamp, method, path, organisation_id,
    user_id, response status, duration_ms. Also sets request_id on request.state.
    """

    async def dispatch(self, request: Request, call_next):
        request_id = _uuid.uuid4()
        request.state.request_id = request_id

        start_time = time.perf_counter()

        # Try to extract user info from JWT for logging (best effort)
        org_id = None
        user_id = None
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            try:
                from jose import jwt, JWTError
                from app.config import get_settings

                settings = get_settings()
                token = auth_header[7:]
                payload = jwt.decode(
                    token,
                    settings.JWT_SECRET_KEY,
                    algorithms=[settings.JWT_ALGORITHM],
                )
                org_id = payload.get("org_id")
                user_id = payload.get("sub")
            except Exception:
                pass

        response = await call_next(request)

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

        logger.info(
            "request_completed",
            request_id=str(request_id),
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
            organisation_id=org_id,
            user_id=user_id,
        )

        # Add request_id to response headers
        response.headers["X-Request-ID"] = str(request_id)

        return response
