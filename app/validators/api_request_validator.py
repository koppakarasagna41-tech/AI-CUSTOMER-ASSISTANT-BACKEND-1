"""
app/validators/api_request_validator.py
─────────────────────────────────────────
API-level request validators.

Provides reusable FastAPI dependency functions that validate common
query parameters and raise HTTPException with meaningful messages.

Usage in a router:
    @router.get("/items")
    async def list_items(
        params: PaginationParams = Depends(get_pagination_params),
        sort:   SortParams       = Depends(get_sort_params(["name","created_at"])),
    ):
        ...
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

from fastapi import Query, HTTPException, status


# ── Pagination ────────────────────────────────────────────────

@dataclass
class PaginationParams:
    page:      int
    page_size: int
    skip:      int  # computed: (page-1)*page_size


def get_pagination_params(
    page:      int = Query(1,   ge=1,   le=10_000, description="Page number (1-based)"),
    page_size: int = Query(20,  ge=1,   le=100,    description="Items per page (max 100)"),
) -> PaginationParams:
    return PaginationParams(
        page=page,
        page_size=page_size,
        skip=(page - 1) * page_size,
    )


# ── Sorting ───────────────────────────────────────────────────

@dataclass
class SortParams:
    sort_by:    str
    sort_order: str
    direction:  int   # 1 = ASC, -1 = DESC


def get_sort_params(allowed_fields: list[str], default_field: str = "created_at"):
    """
    Factory returning a FastAPI dependency that validates sort parameters.

    Usage:
        SortDep = get_sort_params(["name", "created_at", "updated_at"])

        @router.get("/")
        async def handler(sort: SortParams = Depends(SortDep)):
            ...
    """
    def _dep(
        sort_by:    str = Query(default_field, description=f"Sort field. Allowed: {', '.join(allowed_fields)}"),
        sort_order: str = Query("desc",        description="Sort direction: asc | desc"),
    ) -> SortParams:
        if sort_by not in allowed_fields:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "success":    False,
                    "message":    f"Invalid sort field '{sort_by}'.",
                    "error_code": "SORT_FIELD_INVALID",
                    "details":    [{"field": "sort_by", "allowed": allowed_fields}],
                },
            )
        if sort_order not in ("asc", "desc"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "success":    False,
                    "message":    "sort_order must be 'asc' or 'desc'.",
                    "error_code": "SORT_ORDER_INVALID",
                    "details":    [{"field": "sort_order", "allowed": ["asc", "desc"]}],
                },
            )
        return SortParams(
            sort_by=sort_by,
            sort_order=sort_order,
            direction=1 if sort_order == "asc" else -1,
        )

    return _dep


# ── Date range ────────────────────────────────────────────────

from datetime import datetime


@dataclass
class DateRangeParams:
    date_from: Optional[datetime]
    date_to:   Optional[datetime]


def get_date_range_params(
    date_from: Optional[datetime] = Query(None, description="Filter from date (ISO format)"),
    date_to:   Optional[datetime] = Query(None, description="Filter to date (ISO format)"),
) -> DateRangeParams:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "success":    False,
                "message":    "date_from must be before date_to.",
                "error_code": "DATE_RANGE_INVALID",
            },
        )
    return DateRangeParams(date_from=date_from, date_to=date_to)


# ── Enum param validator ──────────────────────────────────────

def validate_enum_param(value: Optional[str], allowed: list[str], field_name: str) -> None:
    """
    Raise HTTPException if value is set and not in allowed list.
    Call inside route handlers for optional enum query params.
    """
    if value is not None and value not in allowed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "success":    False,
                "message":    f"Invalid value '{value}' for '{field_name}'.",
                "error_code": "PARAM_INVALID",
                "details":    [{"field": field_name, "allowed": allowed}],
            },
        )


# ── Rate-limit hint (informational — real limiting via middleware) ────

MAX_BATCH_SIZE = 20


def validate_batch_size(items: list, label: str = "items") -> None:
    """Raise HTTPException if batch exceeds the allowed maximum."""
    if len(items) > MAX_BATCH_SIZE:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "success":    False,
                "message":    f"Batch too large. Maximum {MAX_BATCH_SIZE} {label} per request.",
                "error_code": "BATCH_TOO_LARGE",
            },
        )
