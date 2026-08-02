"""
app/routers/tickets.py
───────────────────────
Ticket Management API — all endpoints with auto-classification.

POST   /tickets              — Create ticket (auto-classify with Gemini)
GET    /tickets              — List tickets (filter by status/category/priority)
GET    /tickets/stats        — Aggregated counts by status/category/priority
GET    /tickets/categories   — List all supported ticket categories
POST   /tickets/{id}/classify — Re-classify an existing ticket with Gemini
GET    /tickets/{id}         — Get ticket by MongoDB _id OR ticket_id
PATCH  /tickets/{id}         — Update ticket fields
DELETE /tickets/{id}         — Delete ticket (admin only)
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from motor.motor_asyncio import AsyncIOMotorCollection

from app.core.auth_deps  import get_current_user, require_admin
from app.core.exceptions import BadRequestError, NotFoundError
from app.core.responses  import success_response, paginated_response
from app.database        import TicketsCollection
from app.models.ticket   import TicketCategory, TicketPriority, TicketStatus
from app.models.user     import UserRole
from app.schemas.ticket  import (
    ClassificationDetail,
    TicketCreate, TicketOut, TicketUpdate,
    TicketClassifyRequest, TicketStatsOut,
)
from app.services.ticket_service import (
    create_ticket,
    get_ticket_by_obj_id,
    get_ticket_by_ticket_id,
    list_tickets,
    update_ticket,
    reclassify_ticket,
    delete_ticket,
    get_ticket_stats,
)
from app.services.ticket_classifier import CATEGORY_META

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tickets", tags=["Tickets"])


# ── Helper: raw doc → TicketOut ───────────────────────────────

def _to_out(doc: dict) -> dict:
    classification = ClassificationDetail(
        category=doc.get("category", "general_inquiry"),
        confidence=doc.get("category_confidence", 0.0),
        auto=doc.get("auto_classified", True),
        model_used=doc.get("classification_model"),
    )
    return TicketOut(
        **{**doc, "id": doc["_id"]},
        classification=classification,
    ).model_dump()


# ── POST /tickets ─────────────────────────────────────────────

@router.post(
    "",
    status_code=201,
    summary="Create a ticket — auto-classifies category and priority with Gemini",
)
async def create_ticket_endpoint(
    payload:      TicketCreate,
    current_user: dict                   = Depends(get_current_user),
    col:          AsyncIOMotorCollection = Depends(TicketsCollection),
):
    """
    Create a support ticket.

    - If `category` is omitted → Gemini classifies from subject + description.
    - If `priority` is omitted → auto-assigned based on category + keywords.
    - Ticket number is auto-generated: `TKT-YYYYMMDD-XXXXXXXX`.
    """
    if not payload.subject.strip():
        raise BadRequestError("Subject cannot be empty.", error_code="EMPTY_SUBJECT")

    if payload.user_id and current_user.get("role") != UserRole.ADMIN.value:
        raise BadRequestError(
            "Only administrators may create tickets for other users.",
            error_code="INVALID_USER_ID",
        )

    user_id = payload.user_id if payload.user_id and current_user.get("role") == UserRole.ADMIN.value else current_user.get("_id")

    doc = await create_ticket(
        col=col,
        subject=payload.subject,
        description=payload.description,
        user_id=user_id,
        conversation_id=payload.conversation_id,
        category=payload.category,
        priority=payload.priority,
        tags=payload.tags,
    )

    return success_response(
        data=_to_out(doc),
        message=(
            f"Ticket {doc['ticket_id']} created "
            f"[{doc['category']} / {doc['priority']}]."
        ),
    )


# ── GET /tickets/stats ────────────────────────────────────────

@router.get(
    "/stats",
    summary="Aggregated ticket counts by status, category, and priority",
)
async def ticket_stats(
    current_user: dict                   = Depends(get_current_user),
    col:          AsyncIOMotorCollection = Depends(TicketsCollection),
):
    """
    Admins and agents see the full ticket universe.
    Customers see only their own.
    """
    role    = current_user.get("role", "customer")
    user_id = None if role in {"admin", "agent"} else current_user.get("_id")

    stats = await get_ticket_stats(col, user_id=user_id)

    return success_response(
        data=TicketStatsOut(**stats).model_dump(),
        message="Ticket statistics retrieved.",
    )


# ── GET /tickets/categories ───────────────────────────────────

@router.get(
    "/categories",
    summary="List all supported ticket categories with metadata",
)
async def list_categories(
    current_user: dict = Depends(get_current_user),
):
    data = [
        {
            "category":         k,
            "description":      v["description"],
            "examples":         v["examples"],
            "default_priority": v["default_priority"].value,
        }
        for k, v in CATEGORY_META.items()
    ]
    return success_response(
        data=data,
        message=f"{len(data)} ticket categories supported.",
    )


# ── GET /tickets ──────────────────────────────────────────────

@router.get(
    "",
    summary="List tickets with optional filters",
)
async def list_tickets_endpoint(
    page:         int           = Query(1,    ge=1),
    page_size:    int           = Query(20,   ge=1, le=100),
    status:       Optional[str] = Query(None, description="Filter by status"),
    category:     Optional[str] = Query(None, description="Filter by category"),
    priority:     Optional[str] = Query(None, description="Filter by priority"),
    search:       Optional[str] = Query(None, description="Search subject/description/ticket_id"),
    current_user: dict                   = Depends(get_current_user),
    col:          AsyncIOMotorCollection = Depends(TicketsCollection),
):
    role    = current_user.get("role", "customer")
    user_id = current_user.get("_id") if role != "admin" else None

    skip        = (page - 1) * page_size
    docs, total = await list_tickets(
        col=col,
        skip=skip, limit=page_size,
        status=status,
        category=category,
        priority=priority,
        user_id=user_id,
        search=search,
    )

    items = [_to_out(d) for d in docs]
    return paginated_response(
        data=items, total_items=total,
        page=page, page_size=page_size,
        message="Tickets retrieved.",
    )


# ── POST /tickets/{id}/classify ───────────────────────────────

@router.post(
    "/{ticket_id}/classify",
    summary="Re-classify an existing ticket using Gemini",
)
async def classify_ticket_endpoint(
    ticket_id:    str,
    current_user: dict                   = Depends(get_current_user),
    col:          AsyncIOMotorCollection = Depends(TicketsCollection),
):
    """
    Re-run Gemini classification on an existing ticket.
    Updates category, priority, confidence, and model metadata.
    """
    # Support both MongoDB _id and human-readable ticket_id
    doc = await get_ticket_by_ticket_id(col, ticket_id)
    if not doc:
        doc = await get_ticket_by_obj_id(col, ticket_id)
    if not doc:
        raise NotFoundError(
            f"Ticket '{ticket_id}' not found.",
            error_code="TICKET_NOT_FOUND",
        )

    updated = await reclassify_ticket(col, doc["_id"])
    return success_response(
        data=_to_out(updated),
        message=(
            f"Ticket re-classified: "
            f"{updated['category']} / {updated['priority']} "
            f"(confidence {updated['category_confidence']:.0%})."
        ),
    )


# ── GET /tickets/{id} ─────────────────────────────────────────

@router.get(
    "/{ticket_id}",
    summary="Get a ticket by its ticket_id (TKT-...) or MongoDB _id",
)
async def get_ticket_endpoint(
    ticket_id:    str,
    current_user: dict                   = Depends(get_current_user),
    col:          AsyncIOMotorCollection = Depends(TicketsCollection),
):
    # Try human-readable ID first, then MongoDB ObjectId
    doc = await get_ticket_by_ticket_id(col, ticket_id)
    if not doc:
        doc = await get_ticket_by_obj_id(col, ticket_id)
    if not doc:
        raise NotFoundError(
            f"Ticket '{ticket_id}' not found.",
            error_code="TICKET_NOT_FOUND",
        )

    # Ownership check for customers only.
    role = current_user.get("role", "customer")
    if role not in {"admin", "agent"} and doc.get("user_id") != current_user.get("_id"):
        raise NotFoundError(
            f"Ticket '{ticket_id}' not found.",
            error_code="TICKET_NOT_FOUND",
        )

    return success_response(
        data=_to_out(doc),
        message="Ticket retrieved.",
    )


# ── PATCH /tickets/{id} ───────────────────────────────────────

@router.patch(
    "/{ticket_id}",
    summary="Update a ticket",
)
async def update_ticket_endpoint(
    ticket_id:    str,
    payload:      TicketUpdate,
    current_user: dict                   = Depends(get_current_user),
    col:          AsyncIOMotorCollection = Depends(TicketsCollection),
):
    doc = await get_ticket_by_ticket_id(col, ticket_id)
    if not doc:
        doc = await get_ticket_by_obj_id(col, ticket_id)
    if not doc:
        raise NotFoundError(
            f"Ticket '{ticket_id}' not found.",
            error_code="TICKET_NOT_FOUND",
        )

    patch = {
        k: (v.value if hasattr(v, "value") else v)
        for k, v in payload.model_dump().items()
        if v is not None
    }
    if not patch:
        raise BadRequestError(
            "No fields to update provided.",
            error_code="NO_UPDATE_FIELDS",
        )

    updated = await update_ticket(col, doc["_id"], patch)
    return success_response(
        data=_to_out(updated),
        message="Ticket updated.",
    )


# ── DELETE /tickets/{id} ──────────────────────────────────────

@router.delete(
    "/{ticket_id}",
    summary="Delete a ticket (admin only)",
)
async def delete_ticket_endpoint(
    ticket_id:    str,
    current_user: dict                   = Depends(require_admin),
    col:          AsyncIOMotorCollection = Depends(TicketsCollection),
):
    doc = await get_ticket_by_ticket_id(col, ticket_id)
    if not doc:
        doc = await get_ticket_by_obj_id(col, ticket_id)
    if not doc:
        raise NotFoundError(
            f"Ticket '{ticket_id}' not found.",
            error_code="TICKET_NOT_FOUND",
        )

    await delete_ticket(col, doc["_id"])
    return success_response(
        data={"ticket_id": doc["ticket_id"]},
        message=f"Ticket {doc['ticket_id']} deleted.",
    )
