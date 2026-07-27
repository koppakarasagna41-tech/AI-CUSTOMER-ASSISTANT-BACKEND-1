"""
app/core/responses.py
──────────────────────
Unified API response envelope.

Every endpoint returns one of:
    {
        "success": true,
        "message": "...",
        "data": {...} | [...] | null,
        "meta": {...} | null          # pagination, totals, etc.
    }

or on error:
    {
        "success": false,
        "message": "...",
        "error_code": "NOT_FOUND",
        "details": [...] | null
    }

Using a consistent envelope makes frontend integration predictable and
allows global error handling without inspecting HTTP status codes alone.
"""

from typing import Any, Generic, List, Optional, TypeVar
from pydantic import BaseModel

DataT = TypeVar("DataT")


# ── Envelope models ───────────────────────────────────────────

class PaginationMeta(BaseModel):
    """Pagination metadata returned with list endpoints."""
    page:        int
    page_size:   int
    total_items: int
    total_pages: int


class APIResponse(BaseModel, Generic[DataT]):
    """
    Standard success response wrapper.

    Usage:
        return APIResponse[UserOut](
            success=True,
            message="User retrieved.",
            data=user_out,
        )
    """
    success:  bool              = True
    message:  str               = "OK"
    data:     Optional[DataT]   = None
    meta:     Optional[Any]     = None   # PaginationMeta or any extra info


class ErrorResponse(BaseModel):
    """Standard error response wrapper (used by exception handlers)."""
    success:    bool            = False
    message:    str
    error_code: Optional[str]   = None
    details:    Optional[Any]   = None


# ── Factory helpers ───────────────────────────────────────────

def success_response(
    data:    Any             = None,
    message: str             = "OK",
    meta:    Optional[Any]   = None,
) -> dict:
    """
    Build a standardised success dict ready to return from a route.

    Returning a dict (not a model instance) lets FastAPI serialise it
    with the route's response_model automatically.
    """
    return {
        "success": True,
        "message": message,
        "data":    data,
        "meta":    meta,
    }


def error_response(
    message:    str,
    error_code: Optional[str] = None,
    details:    Optional[Any] = None,
) -> dict:
    """Build a standardised error dict (used inside exception handlers)."""
    return {
        "success":    False,
        "message":    message,
        "error_code": error_code,
        "details":    details,
    }


def paginated_response(
    data:        List[Any],
    total_items: int,
    page:        int,
    page_size:   int,
    message:     str = "OK",
) -> dict:
    """
    Convenience helper for list endpoints with pagination.

    Usage:
        return paginated_response(
            data=items,
            total_items=total,
            page=page,
            page_size=page_size,
            message="Conversations retrieved.",
        )
    """
    import math
    total_pages = math.ceil(total_items / page_size) if page_size > 0 else 0
    meta = PaginationMeta(
        page=page,
        page_size=page_size,
        total_items=total_items,
        total_pages=total_pages,
    )
    return success_response(data=data, message=message, meta=meta.model_dump())
