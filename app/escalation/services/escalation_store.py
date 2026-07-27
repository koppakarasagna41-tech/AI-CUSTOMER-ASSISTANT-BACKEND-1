"""
app/escalation/services/escalation_store.py
─────────────────────────────────────────────
MongoDB persistence for escalation events.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorCollection
from pymongo import DESCENDING

from app.escalation.services.detector import DetectedSignal
from app.utils.helpers import utc_now

logger = logging.getLogger(__name__)


def _gen_escalation_id() -> str:
    date = datetime.now(tz=timezone.utc).strftime("%Y%m%d")
    return f"ESC-{date}-{uuid.uuid4().hex[:8].upper()}"


async def save_escalation_event(
    col:             AsyncIOMotorCollection,
    conversation_id: str,
    signal:          DetectedSignal,
    user_id:         Optional[str] = None,
    ticket_id:       Optional[str] = None,
) -> str:
    """Persist one escalation event. Returns escalation_id."""
    esc_id = _gen_escalation_id()
    now    = utc_now()

    doc = {
        "escalation_id":   esc_id,
        "conversation_id": conversation_id,
        "user_id":         user_id,
        "ticket_id":       ticket_id,
        "trigger":         signal.trigger,
        "priority":        signal.priority,
        "description":     signal.description,
        "state":           "open",
        "evidence":        signal.evidence,
        "assigned_to":     None,
        "resolved_at":     None,
        "resolution_note": None,
        "admin_notified":  False,
        "notified_at":     None,
        "created_at":      now,
        "updated_at":      now,
    }
    await col.insert_one(doc)
    logger.info(
        "Escalation event saved",
        extra={
            "component": "app",
            "event": "escalation_saved",
            "escalation_id": esc_id,
            "conversation_id": conversation_id,
            "user_id": user_id,
            "confidence_score": getattr(signal, "confidence_score", None),
            "reason": getattr(signal, "description", None),
            "trigger": signal.trigger,
            "priority": signal.priority,
        },
    )
    return esc_id


async def get_escalation_event(
    col: AsyncIOMotorCollection,
    escalation_id: str,
) -> Optional[dict]:
    doc = await col.find_one({"escalation_id": escalation_id})
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc


async def list_escalation_events(
    col:             AsyncIOMotorCollection,
    skip:            int           = 0,
    limit:           int           = 20,
    state:           Optional[str] = None,
    trigger:         Optional[str] = None,
    priority:        Optional[str] = None,
    conversation_id: Optional[str] = None,
    user_id:         Optional[str] = None,
) -> tuple[list[dict], int]:
    query: dict = {}
    if state:           query["state"]           = state
    if trigger:         query["trigger"]         = trigger
    if priority:        query["priority"]        = priority
    if conversation_id: query["conversation_id"] = conversation_id
    if user_id:         query["user_id"]         = user_id

    total  = await col.count_documents(query)
    cursor = col.find(query).sort("created_at", DESCENDING).skip(skip).limit(limit)
    docs   = await cursor.to_list(length=limit)
    for doc in docs:
        doc["_id"] = str(doc["_id"])
    return docs, total


async def get_conversation_escalations(
    col:             AsyncIOMotorCollection,
    conversation_id: str,
) -> list[dict]:
    cursor = col.find({"conversation_id": conversation_id}).sort("created_at", 1)
    docs   = await cursor.to_list(length=100)
    for doc in docs:
        doc["_id"] = str(doc["_id"])
    return docs


async def update_escalation_event(
    col:           AsyncIOMotorCollection,
    escalation_id: str,
    patch:         dict,
) -> bool:
    patch["updated_at"] = utc_now()
    result = await col.update_one({"escalation_id": escalation_id}, {"$set": patch})
    return result.modified_count > 0


async def mark_admin_notified(
    col:           AsyncIOMotorCollection,
    escalation_id: str,
) -> None:
    now = utc_now()
    await col.update_one(
        {"escalation_id": escalation_id},
        {"$set": {"admin_notified": True, "notified_at": now, "updated_at": now}},
    )


async def escalation_summary(
    col: AsyncIOMotorCollection,
) -> dict:
    async def _count_by(field: str) -> dict[str, int]:
        pipeline = [
            {"$group": {"_id": f"${field}", "count": {"$sum": 1}}},
            {"$project": {"key": "$_id", "count": 1, "_id": 0}},
        ]
        rows = await col.aggregate(pipeline).to_list(length=50)
        return {r["key"]: r["count"] for r in rows if r.get("key")}

    total       = await col.count_documents({})
    by_state    = await _count_by("state")
    by_trigger  = await _count_by("trigger")
    by_priority = await _count_by("priority")

    return {
        "total":       total,
        "by_state":    by_state,
        "by_trigger":  by_trigger,
        "by_priority": by_priority,
    }
