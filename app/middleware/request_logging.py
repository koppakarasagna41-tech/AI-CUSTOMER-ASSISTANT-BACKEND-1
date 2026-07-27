"""
app/middleware/request_logging.py
───────────────────────────────────
ASGI middleware that logs every inbound request and its response.
"""

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

# Paths to suppress from INFO-level logging
_QUIET_PATHS = {"/health", "/favicon.ico"}


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.perf_counter()

        client_ip = (
            request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
            or request.headers.get("X-Real-IP", "")
            or (request.client.host if request.client else "unknown")
        )

        try:
            response: Response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.exception(
                "API request failed",
                extra={
                    "component": "api",
                    "event": "request_failed",
                    "method": request.method,
                    "path": request.url.path,
                    "query": request.url.query,
                    "url": str(request.url),
                    "status_code": 500,
                    "client_ip": client_ip,
                    "duration_ms": round(duration_ms, 3),
                },
            )
            raise

        duration_ms = (time.perf_counter() - start) * 1000
        log_level = logging.DEBUG if request.url.path in _QUIET_PATHS else logging.INFO

        logger.log(
            log_level,
            "API request completed",
            extra={
                "component": "api",
                "event": "request_completed",
                "method": request.method,
                "path": request.url.path,
                "query": request.url.query,
                "url": str(request.url),
                "status_code": response.status_code,
                "client_ip": client_ip,
                "duration_ms": round(duration_ms, 3),
            },
        )

        response.headers["X-Process-Time-Ms"] = f"{duration_ms:.1f}"
        return response
