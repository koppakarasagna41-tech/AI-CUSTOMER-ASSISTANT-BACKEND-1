"""
app/services/ticket_service.py
────────────────────────────────
Business logic layer for ticket management.

Responsibilities:
  - Create ticket with auto-classification
  - CRUD operations
  - Re-classify an existing ticket
  - Stats aggregation
  - Ticket number generation (TKT-YYYYMMDD-XXXXXXXX)

Never contains routing logic — called only from routers.
"""

import logging
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorCollection
from pymongo import DESCENDING

from app.database.crud import (
    create_document,
    get_document,
    get_document_by_id,
    get_documents,
    count_documents,
    update_document,
    update_document_by_id,
    delete_document_by_id,
)
from app.models.ticket    import TicketCategory, TicketPriority, TicketStatus
from app.services.ticket_classifier import classify_ticket, auto_priority
from app.utils.helpers    import utc_now, generate_ticket_id
from app.core.exceptions  import NotFoundError

logger = logging.getLogger(__name__)


# ── Create ────────────────────────────────────────────────────

async def create_ticket(
    col:             AsyncIOMotorCollection,
    subject:         str,
    description:     Optional[str]         = None,
    user_id:         Optional[str]         = None,
    conversation_id: Optional[str]         = None,
    category:        Optional[TicketCategory] = None,
    priority:        Optional[TicketPriority] = None,
    tags:            list[str]             = None,
) -> dict:
    """
    Create a new ticket.

    If `category` is None → auto-classify with Gemini.
    If `priority` is None → auto-assign from category + keywords.
    Returns the full saved document (no password fields — tickets don't have any).
    """
    now    = utc_now()
    tags   = tags or []

    # ── Auto-classify ─────────────────────────────────────────
    if category is None:
        result = await classify_ticket(subject, description)
        final_category   = result.category
        final_priority   = priority or result.priority
        confidence       = result.confidence
        auto_classified  = True
        classification_model = result.model_used
    else:
        final_category   = category
        final_priority   = priority or auto_priority(
            (subject + " " + (description or "")), category
        )
        confidence       = 1.0
        auto_classified  = False
        classification_model = None

    ticket_id = generate_ticket_id()

    doc = {
        "ticket_id":            ticket_id,
        "user_id":              user_id,
        "conversation_id":      conversation_id,
        "subject":              subject.strip(),
        "description":          description.strip() if description else None,
        "category":             final_category.value,
        "status":               TicketStatus.OPEN.value,
        "priority":             final_priority.value,
        "assigned_to":          None,
        "resolved_at":          None,
        "category_confidence":  round(confidence, 4),
        "auto_classified":      auto_classified,
        "classification_model": classification_model,
        "tags":                 tags,
        "metadata":             {},
        "created_at":           now,
        "updated_at":           now,
    }

    inserted_id = await create_document(col, doc)
    created     = await get_document_by_id(col, inserted_id)

    logger.info(
        "Ticket created | id=%s category=%s priority=%s auto=%s",
        ticket_id, final_category.value, final_priority.value, auto_classified,
    )
    return created


# ── Read ──────────────────────────────────────────────────────

async def get_ticket_by_obj_id(
    col: AsyncIOMotorCollection,
    obj_id: str,
) -> Optional[dict]:
    return await get_document_by_id(col, obj_id)


async def get_ticket_by_ticket_id(
    col:       AsyncIOMotorCollection,
    ticket_id: str,
) -> Optional[dict]:
    return await get_document(col, {"ticket_id": ticket_id})


async def list_tickets(
    col:      AsyncIOMotorCollection,
    skip:     int           = 0,
    limit:    int           = 20,
    status:   Optional[str] = None,
    category: Optional[str] = None,
    priority: Optional[str] = None,
    user_id:  Optional[str] = None,
    search:   Optional[str] = None,
) -> tuple[list[dict], int]:
    query: dict = {}
    if status:   query["status"]   = status
    if category: query["category"] = category
    if priority: query["priority"] = priority
    if user_id:  query["user_id"]  = user_id
    if search:
        query["$or"] = [
            {"subject":     {"$regex": search, "$options": "i"}},
            {"description": {"$regex": search, "$options": "i"}},
            {"ticket_id":   {"$regex": search, "$options": "i"}},
        ]

    total = await count_documents(col, query)
    docs  = await get_documents(
        col, filter_query=query,
        skip=skip, limit=limit,
        sort=[("created_at", DESCENDING)],
    )
    return docs, total


# ── Update ────────────────────────────────────────────────────

async def update_ticket(
    col:       AsyncIOMotorCollection,
    obj_id:    str,
    patch:     dict,
) -> Optional[dict]:
    patch["updated_at"] = utc_now()

    # Auto-set resolved_at when status changes to resolved/closed
    if patch.get("status") in (TicketStatus.RESOLVED.value, TicketStatus.CLOSED.value):
        patch.setdefault("resolved_at", utc_now().isoformat())

    updated = await update_document_by_id(col, obj_id, {"$set": patch})
    if not updated:
        return None
    return await get_document_by_id(col, obj_id)


# ── Re-classify ───────────────────────────────────────────────

async def reclassify_ticket(
    col:    AsyncIOMotorCollection,
    obj_id: str,
) -> Optional[dict]:
    """
    Re-run Gemini classification on an existing ticket and update
    its category, priority, and classification metadata.
    """
    doc = await get_document_by_id(col, obj_id)
    if not doc:
        return None

    result = await classify_ticket(
        doc.get("subject", ""),
        doc.get("description"),
    )

    patch = {
        "category":             result.category.value,
        "priority":             result.priority.value,
        "category_confidence":  round(result.confidence, 4),
        "auto_classified":      True,
        "classification_model": result.model_used,
        "updated_at":           utc_now(),
    }

    await update_document_by_id(col, obj_id, {"$set": patch})
    updated = await get_document_by_id(col, obj_id)

    logger.info(
        "Ticket re-classified | id=%s category=%s priority=%s confidence=%.3f",
        doc.get("ticket_id"), result.category.value,
        result.priority.value, result.confidence,
    )
    return updated


# ── Delete ────────────────────────────────────────────────────

async def delete_ticket(
    col:    AsyncIOMotorCollection,
    obj_id: str,
) -> bool:
    return await delete_document_by_id(col, obj_id)


# ── Stats ─────────────────────────────────────────────────────

async def get_ticket_stats(
    col:     AsyncIOMotorCollection,
    user_id: Optional[str] = None,
) -> dict:
    """
    Return aggregated counts: total, by_status, by_category, by_priority.
    """
    match = {"user_id": user_id} if user_id else {}

    async def _count_by(field: str) -> dict[str, int]:
        pipeline = [
            {"$match": match},
            {"$group": {"_id": f"${field}", "count": {"$sum": 1}}},
        ]
        cursor = col.aggregate(pipeline)
        rows   = await cursor.to_list(length=50)
        return {r["_id"]: r["count"] for r in rows if r["_id"]}

    total        = await count_documents(col, match)
    by_status    = await _count_by("status")
    by_category  = await _count_by("category")
    by_priority  = await _count_by("priority")

    return {
        "total":       total,
        "by_status":   by_status,
        "by_category": by_category,
        "by_priority": by_priority,
    }
