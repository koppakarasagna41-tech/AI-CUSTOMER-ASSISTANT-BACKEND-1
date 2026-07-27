"""
app/intent/services/intent_store.py
─────────────────────────────────────
MongoDB persistence layer for intent logs.

Provides:
  save_intent_log()       — insert a classification result
  get_intent_log()        — fetch by intent_id
  list_intent_logs()      — paginated list with filters
  get_conversation_intents() — all intents for one conversation
  intent_summary()        — aggregate counts by intent
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorCollection
from pymongo import DESCENDING

from app.intent.services.classifier import ClassificationResult
from app.utils.helpers               import utc_now

logger = logging.getLogger(__name__)


def _gen_intent_id() -> str:
    date = datetime.now(tz=timezone.utc).strftime("%Y%m%d")
    uid  = uuid.uuid4().hex[:8].upper()
    return f"ILD-{date}-{uid}"


async def save_intent_log(
    col:             AsyncIOMotorCollection,
    result:          ClassificationResult,
    user_id:         Optional[str] = None,
    conversation_id: Optional[str] = None,
) -> str:
    """
    Persist a ClassificationResult to MongoDB.

    Returns the generated intent_id string.
    """
    intent_id = _gen_intent_id()
    now       = utc_now()

    doc = {
        "intent_id":        intent_id,
        "conversation_id":  conversation_id,
        "user_id":          user_id,
        "message":          result.message,
        "intent":           result.intent,
        "confidence":       result.confidence,
        "all_scores":       result.all_scores,
        "model_used":       result.model_used,
        "tokens_used":      result.tokens_used,
        "is_fallback":      result.is_fallback,
        "latency_ms":       result.latency_ms,
        "created_at":       now,
        "updated_at":       now,
    }

    await col.insert_one(doc)
    logger.debug("Intent log saved | id=%s intent=%s", intent_id, result.intent)
    return intent_id


async def get_intent_log(
    col:       AsyncIOMotorCollection,
    intent_id: str,
) -> Optional[dict]:
    """Fetch a single intent log by its intent_id."""
    doc = await col.find_one({"intent_id": intent_id})
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc


async def list_intent_logs(
    col:             AsyncIOMotorCollection,
    skip:            int           = 0,
    limit:           int           = 20,
    intent:          Optional[str] = None,
    user_id:         Optional[str] = None,
    conversation_id: Optional[str] = None,
    is_fallback:     Optional[bool] = None,
) -> tuple[list[dict], int]:
    """
    Return (logs, total_count) with optional filters.
    """
    query: dict = {}
    if intent:          query["intent"]          = intent
    if user_id:         query["user_id"]         = user_id
    if conversation_id: query["conversation_id"] = conversation_id
    if is_fallback is not None:
        query["is_fallback"] = is_fallback

    total  = await col.count_documents(query)
    cursor = (
        col.find(query)
        .sort("created_at", DESCENDING)
        .skip(skip)
        .limit(limit)
    )
    docs = await cursor.to_list(length=limit)
    for doc in docs:
        doc["_id"] = str(doc["_id"])
    return docs, total


async def get_conversation_intents(
    col:             AsyncIOMotorCollection,
    conversation_id: str,
) -> list[dict]:
    """Return all intent logs for a conversation, oldest first."""
    cursor = (
        col.find({"conversation_id": conversation_id})
        .sort("created_at", 1)
    )
    docs = await cursor.to_list(length=200)
    for doc in docs:
        doc["_id"] = str(doc["_id"])
    return docs


async def intent_summary(
    col:     AsyncIOMotorCollection,
    user_id: Optional[str] = None,
) -> list[dict]:
    """
    Return aggregated intent counts.
    e.g. [{"intent": "billing", "count": 42}, ...]
    """
    match_stage: dict = {}
    if user_id:
        match_stage = {"$match": {"user_id": user_id}}
    else:
        match_stage = {"$match": {}}

    pipeline = [
        match_stage,
        {"$group": {"_id": "$intent", "count": {"$sum": 1}}},
        {"$project": {"intent": "$_id", "count": 1, "_id": 0}},
        {"$sort": {"count": -1}},
    ]
    cursor = col.aggregate(pipeline)
    return await cursor.to_list(length=50)
