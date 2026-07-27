"""
app/sentiment/services/sentiment_store.py
──────────────────────────────────────────
MongoDB persistence for sentiment analysis results.

Also handles updating the conversation document with the latest
aggregate sentiment so conversations are always in sync.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorCollection
from pymongo import ASCENDING, DESCENDING

from app.sentiment.services.analyzer import AnalysisResult
from app.utils.helpers import utc_now

logger = logging.getLogger(__name__)


def _gen_sentiment_id() -> str:
    date = datetime.now(tz=timezone.utc).strftime("%Y%m%d")
    uid  = uuid.uuid4().hex[:8].upper()
    return f"SID-{date}-{uid}"


# ── Save single sentiment log ─────────────────────────────────

async def save_sentiment_log(
    col:             AsyncIOMotorCollection,
    result:          AnalysisResult,
    user_id:         Optional[str] = None,
    conversation_id: Optional[str] = None,
    message_id:      Optional[str] = None,
    source:          str           = "message",
) -> str:
    """Persist one AnalysisResult. Returns the generated sentiment_id."""
    sentiment_id = _gen_sentiment_id()
    now          = utc_now()

    doc = {
        "sentiment_id":   sentiment_id,
        "conversation_id": conversation_id,
        "message_id":     message_id,
        "user_id":        user_id,
        "text":           result.text,
        "source":         source,
        "sentiment":      result.sentiment,
        "confidence":     result.confidence,
        "polarity_score": result.polarity_score,
        "all_scores":     result.all_scores,
        "model_used":     result.model_used,
        "tokens_used":    result.tokens_used,
        "is_fallback":    result.is_fallback,
        "latency_ms":     result.latency_ms,
        "created_at":     now,
        "updated_at":     now,
    }
    await col.insert_one(doc)
    logger.debug(
        "Sentiment log saved | id=%s sentiment=%s conv=%s",
        sentiment_id, result.sentiment, conversation_id,
    )
    return sentiment_id


# ── Update conversation with aggregate sentiment ──────────────

async def update_conversation_sentiment(
    conversations_col: AsyncIOMotorCollection,
    conversation_id:   str,
    dominant_sentiment: str,
    average_polarity:   float,
    trend:              str,
) -> None:
    """
    Stamp the conversations document with the latest aggregate sentiment.
    This allows listing conversations filtered/sorted by sentiment
    without re-aggregating every time.
    """
    await conversations_col.update_one(
        {"conversation_id": conversation_id},
        {"$set": {
            "sentiment":           dominant_sentiment,
            "sentiment_polarity":  round(average_polarity, 3),
            "sentiment_trend":     trend,
            "sentiment_updated_at": utc_now().isoformat(),
            "updated_at":          utc_now(),
        }},
    )
    logger.debug(
        "Conversation sentiment updated | conv=%s sentiment=%s polarity=%.3f",
        conversation_id, dominant_sentiment, average_polarity,
    )


# ── Read operations ───────────────────────────────────────────

async def get_sentiment_log(
    col:          AsyncIOMotorCollection,
    sentiment_id: str,
) -> Optional[dict]:
    doc = await col.find_one({"sentiment_id": sentiment_id})
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc


async def list_sentiment_logs(
    col:             AsyncIOMotorCollection,
    skip:            int           = 0,
    limit:           int           = 20,
    sentiment:       Optional[str] = None,
    conversation_id: Optional[str] = None,
    user_id:         Optional[str] = None,
    is_fallback:     Optional[bool] = None,
) -> tuple[list[dict], int]:
    query: dict = {}
    if sentiment:       query["sentiment"]       = sentiment
    if conversation_id: query["conversation_id"] = conversation_id
    if user_id:         query["user_id"]         = user_id
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


async def get_conversation_sentiment_logs(
    col:             AsyncIOMotorCollection,
    conversation_id: str,
) -> list[dict]:
    """All sentiment logs for a conversation, chronological order."""
    cursor = (
        col.find({"conversation_id": conversation_id})
        .sort("created_at", ASCENDING)
    )
    docs = await cursor.to_list(length=500)
    for doc in docs:
        doc["_id"] = str(doc["_id"])
    return docs


async def sentiment_summary(
    col:     AsyncIOMotorCollection,
    user_id: Optional[str] = None,
) -> list[dict]:
    """Aggregate counts per sentiment label."""
    match = {"user_id": user_id} if user_id else {}
    pipeline = [
        {"$match": match},
        {"$group": {"_id": "$sentiment", "count": {"$sum": 1}}},
        {"$project": {"sentiment": "$_id", "count": 1, "_id": 0}},
        {"$sort": {"count": -1}},
    ]
    cursor = col.aggregate(pipeline)
    return await cursor.to_list(length=20)
