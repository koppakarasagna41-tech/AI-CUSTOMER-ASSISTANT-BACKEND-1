"""
app/core/exceptions.py
───────────────────────
Application exception hierarchy + FastAPI exception handlers.

Usage pattern:
    raise NotFoundError("Conversation not found.", error_code="CONV_NOT_FOUND")

The handlers below translate every AppException subclass into the
standard ErrorResponse envelope with the correct HTTP status.

Register all handlers in main.py:
    from app.core.exceptions import register_exception_handlers
    register_exception_handlers(app)
"""

import logging
from typing import Any, Optional

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.responses import error_response

logger = logging.getLogger(__name__)


# ── Exception hierarchy ───────────────────────────────────────

class AppException(Exception):
    """
    Base class for all application exceptions.

    Attributes:
        message    : Human-readable error message.
        error_code : Optional machine-readable code for the frontend.
        status_code: HTTP status to return.
        details    : Optional extra context (field errors, etc.).
    """

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR

    def __init__(
        self,
        message:    str,
        error_code: Optional[str] = None,
        details:    Optional[Any] = None,
    ) -> None:
        self.message    = message
        self.error_code = error_code
        self.details    = details
        super().__init__(message)


class NotFoundError(AppException):
    """Resource does not exist (404)."""
    status_code = status.HTTP_404_NOT_FOUND


class ValidationError(AppException):
    """Business-level validation failure, distinct from Pydantic (422)."""
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY


class DatabaseError(AppException):
    """MongoDB operation failed (500)."""
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR


class UnauthorizedError(AppException):
    """Missing or invalid credentials (401)."""
    status_code = status.HTTP_401_UNAUTHORIZED


class ForbiddenError(AppException):
    """Authenticated but insufficient permissions (403)."""
    status_code = status.HTTP_403_FORBIDDEN


class ConflictError(AppException):
    """Resource already exists or state conflict (409)."""
    status_code = status.HTTP_409_CONFLICT


class BadRequestError(AppException):
    """Malformed request (400)."""
    status_code = status.HTTP_400_BAD_REQUEST


# ── Handlers ─────────────────────────────────────────────────

async def _app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    logger.warning(
        "AppException [%s] %s | path=%s",
        exc.__class__.__name__,
        exc.message,
        request.url.path,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response(
            message=exc.message,
            error_code=exc.error_code,
            details=exc.details,
        ),
    )


async def _http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    logger.warning(
        "HTTPException %s | path=%s | detail=%s",
        exc.status_code,
        request.url.path,
        exc.detail,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response(
            message=str(exc.detail),
            error_code=f"HTTP_{exc.status_code}",
        ),
    )


async def _validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """
    Pydantic request validation errors — returns 422 with field-level details.
    """
    field_errors = []
    for err in exc.errors():
        field_errors.append({
            "field":   " → ".join(str(loc) for loc in err["loc"]),
            "message": err["msg"],
            "type":    err["type"],
        })

    logger.warning(
        "Request validation failed",
        extra={
            "component": "api",
            "event": "validation_error",
            "path": request.url.path,
            "errors": field_errors,
        },
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=error_response(
            message="Request validation failed.",
            error_code="VALIDATION_ERROR",
            details=field_errors,
        ),
    )


async def _unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """
    Catch-all for any unexpected exception — logs a full traceback.
    Returns a generic 500 (no internal details leaked to the client).
    """
    logger.exception(
        "Unhandled exception",
        extra={
            "component": "api",
            "event": "unhandled_exception",
            "path": request.url.path,
            "exception_type": exc.__class__.__name__,
            "exception_message": str(exc),
        },
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_response(
            message="An unexpected error occurred. Please try again later.",
            error_code="INTERNAL_SERVER_ERROR",
        ),
    )


# ── Registration ──────────────────────────────────────────────

def register_exception_handlers(app: FastAPI) -> None:
    """
    Attach all exception handlers to the FastAPI application.
    Call from main.py after creating the app instance.
    """
    app.add_exception_handler(AppException,            _app_exception_handler)       # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException,  _http_exception_handler)      # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError,  _validation_exception_handler) # type: ignore[arg-type]
    app.add_exception_handler(Exception,               _unhandled_exception_handler) # type: ignore[arg-type]
