"""
app/history/services/history_service.py
──────────────────────────────────────────
Conversation History Service.

Assembles rich conversation history by joining:
  - conversations collection  (metadata, sentiment summary)
  - messages collection       (all messages, chronological)
  - intent_logs collection    (per-message intent)
  - sentiment_logs collection (per-message sentiment)
  - tickets collection        (linked tickets)

All reads are async, collections are queried concurrently where possible.
"""

import logging
from datetime import datetime
from typing import Optional

import asyncio
from motor.motor_asyncio import AsyncIOMotorCollection
from pymongo import ASCENDING, DESCENDING

from app.history.schemas.history import (
    MessageHistoryItem, MessageIntentOut, MessageSentimentOut,
    ConversationHistory, ConversationHistoryList,
    ConversationSentimentSummary, LinkedTicket,
    HistoryDeleteResult,
)
from app.sentiment.constants import SENTIMENT_META

logger = logging.getLogger(__name__)


# ── Build a single full conversation history ──────────────────

async def get_conversation_history(
    conversation_id:  str,
    conversations_col: AsyncIOMotorCollection,
    messages_col:      AsyncIOMotorCollection,
    intent_logs_col:   AsyncIOMotorCollection,
    sentiment_logs_col: AsyncIOMotorCollection,
    tickets_col:       AsyncIOMotorCollection,
    msg_page:          int = 1,
    msg_page_size:     int = 50,
) -> Optional[ConversationHistory]:
    """
    Build the full enriched history for one conversation.
    Returns None if the conversation doesn't exist.
    """
    # Fetch conversation
    conv = await conversations_col.find_one({"conversation_id": conversation_id})
    if not conv:
        return None
    conv["_id"] = str(conv["_id"])

    # Fetch messages, intent logs, sentiment logs, tickets — concurrently
    msg_skip = (msg_page - 1) * msg_page_size

    async def _get_messages():
        cursor = (
            messages_col
            .find({"conversation_id": conversation_id})
            .sort("created_at", ASCENDING)
            .skip(msg_skip)
            .limit(msg_page_size)
        )
        docs = await cursor.to_list(length=msg_page_size)
        for d in docs:
            d["_id"] = str(d["_id"])
        return docs

    async def _count_messages():
        return await messages_col.count_documents({"conversation_id": conversation_id})

    async def _get_intents():
        cursor = intent_logs_col.find(
            {"conversation_id": conversation_id},
            {"message_id": 1, "intent": 1, "confidence": 1, "_id": 0},
        )
        rows = await cursor.to_list(length=500)
        # Index by message_id
        return {r["message_id"]: r for r in rows if r.get("message_id")}

    async def _get_sentiments():
        cursor = sentiment_logs_col.find(
            {"conversation_id": conversation_id},
            {"message_id": 1, "sentiment": 1, "confidence": 1, "polarity_score": 1, "_id": 0},
        )
        rows = await cursor.to_list(length=500)
        return {r["message_id"]: r for r in rows if r.get("message_id")}

    async def _get_tickets():
        cursor = tickets_col.find(
            {"conversation_id": conversation_id},
            {"ticket_id": 1, "subject": 1, "category": 1, "priority": 1, "status": 1, "_id": 0},
        )
        return await cursor.to_list(length=20)

    messages, msg_total, intents, sentiments, tickets = await asyncio.gather(
        _get_messages(), _count_messages(),
        _get_intents(), _get_sentiments(), _get_tickets(),
    )

    # ── Enrich messages ───────────────────────────────────────
    enriched: list[MessageHistoryItem] = []
    for msg in messages:
        msg_id = str(msg["_id"])

        intent_data  = intents.get(msg_id)
        sentiment_data = sentiments.get(msg_id)

        intent_out = None
        if intent_data:
            from app.intent.constants import INTENT_META
            meta = INTENT_META.get(intent_data.get("intent", ""), {})
            intent_out = MessageIntentOut(
                intent=intent_data.get("intent"),
                label=meta.get("label"),
                confidence=intent_data.get("confidence"),
            )

        sentiment_out = None
        if sentiment_data:
            sent_key = sentiment_data.get("sentiment", "neutral")
            s_meta   = SENTIMENT_META.get(sent_key, {})
            sentiment_out = MessageSentimentOut(
                sentiment=sent_key,
                label=s_meta.get("label"),
                emoji=s_meta.get("emoji"),
                confidence=sentiment_data.get("confidence"),
                polarity_score=sentiment_data.get("polarity_score"),
            )

        enriched.append(MessageHistoryItem(
            id=msg_id,
            conversation_id=msg.get("conversation_id", conversation_id),
            role=msg.get("role", "user"),
            content=msg.get("content", ""),
            status=msg.get("status"),
            tokens_used=msg.get("tokens_used"),
            model_used=msg.get("model_used"),
            intent=intent_out,
            sentiment=sentiment_out,
            created_at=msg.get("created_at"),
        ))

    # ── Sentiment summary ─────────────────────────────────────
    sentiment_summary = None
    dominant = conv.get("sentiment")
    if dominant:
        s_meta = SENTIMENT_META.get(dominant, {})
        sentiment_summary = ConversationSentimentSummary(
            dominant=dominant,
            dominant_label=s_meta.get("label"),
            emoji=s_meta.get("emoji"),
            avg_polarity=conv.get("sentiment_polarity"),
            trend=conv.get("sentiment_trend"),
        )

    # ── Linked tickets ────────────────────────────────────────
    linked = [
        LinkedTicket(
            ticket_id=t["ticket_id"],
            subject=t.get("subject", ""),
            category=t.get("category", ""),
            priority=t.get("priority", ""),
            status=t.get("status", ""),
        )
        for t in tickets
    ]

    return ConversationHistory(
        id=conv["_id"],
        conversation_id=conversation_id,
        user_id=conv.get("user_id"),
        title=conv.get("title"),
        status=conv.get("status", "open"),
        message_count=conv.get("message_count", 0),
        last_message_at=conv.get("last_message_at"),
        tags=conv.get("tags", []),
        sentiment_summary=sentiment_summary,
        linked_tickets=linked,
        messages=enriched,
        messages_total=msg_total,
        messages_page=msg_page,
        messages_page_size=msg_page_size,
        created_at=conv.get("created_at"),
        updated_at=conv.get("updated_at"),
    )


# ── List / search conversations ───────────────────────────────

async def list_conversation_history(
    conversations_col: AsyncIOMotorCollection,
    tickets_col:       AsyncIOMotorCollection,
    skip:              int            = 0,
    limit:             int            = 20,
    user_id:           Optional[str]  = None,
    status:            Optional[str]  = None,
    sentiment:         Optional[str]  = None,
    has_tickets:       Optional[bool] = None,
    search:            Optional[str]  = None,
    date_from:         Optional[datetime] = None,
    date_to:           Optional[datetime] = None,
    sort_by:           str            = "created_at",
    sort_order:        str            = "desc",
) -> tuple[list[ConversationHistoryList], int]:
    """Return (list of summary items, total_count) with full filter + sort support."""

    query: dict = {}
    if user_id:   query["user_id"] = user_id
    if status:    query["status"]  = status
    if sentiment: query["sentiment"] = sentiment
    if search:
        query["$or"] = [
            {"title":           {"$regex": search, "$options": "i"}},
            {"tags":            {"$regex": search, "$options": "i"}},
            {"conversation_id": {"$regex": search, "$options": "i"}},
        ]
    if date_from or date_to:
        date_q: dict = {}
        if date_from: date_q["$gte"] = date_from
        if date_to:   date_q["$lte"] = date_to
        query["created_at"] = date_q

    # Sort direction
    direction = DESCENDING if sort_order == "desc" else ASCENDING
    valid_sorts = {"created_at", "updated_at", "message_count", "sentiment_polarity"}
    sort_field  = sort_by if sort_by in valid_sorts else "created_at"

    total  = await conversations_col.count_documents(query)
    cursor = (
        conversations_col
        .find(query)
        .sort(sort_field, direction)
        .skip(skip)
        .limit(limit)
    )
    docs = await cursor.to_list(length=limit)

    # Batch-fetch ticket counts for all conversations
    conv_ids   = [d["conversation_id"] for d in docs]
    ticket_map: dict[str, int] = {}
    if conv_ids:
        pipeline = [
            {"$match": {"conversation_id": {"$in": conv_ids}}},
            {"$group": {"_id": "$conversation_id", "count": {"$sum": 1}}},
        ]
        rows = await tickets_col.aggregate(pipeline).to_list(length=len(conv_ids))
        ticket_map = {r["_id"]: r["count"] for r in rows}

    items: list[ConversationHistoryList] = []
    for doc in docs:
        doc["_id"] = str(doc["_id"])
        cid        = doc.get("conversation_id", "")
        t_count    = ticket_map.get(cid, 0)

        items.append(ConversationHistoryList(
            id=doc["_id"],
            conversation_id=cid,
            user_id=doc.get("user_id"),
            title=doc.get("title"),
            status=doc.get("status", "open"),
            message_count=doc.get("message_count", 0),
            last_message_at=doc.get("last_message_at"),
            tags=doc.get("tags", []),
            sentiment=doc.get("sentiment"),
            sentiment_polarity=doc.get("sentiment_polarity"),
            sentiment_trend=doc.get("sentiment_trend"),
            has_tickets=t_count > 0,
            ticket_count=t_count,
            created_at=doc.get("created_at"),
            updated_at=doc.get("updated_at"),
        ))

    return items, total


# ── Delete conversation history ───────────────────────────────

async def delete_conversation_history(
    conversation_id:    str,
    conversations_col:  AsyncIOMotorCollection,
    messages_col:       AsyncIOMotorCollection,
    intent_logs_col:    AsyncIOMotorCollection,
    sentiment_logs_col: AsyncIOMotorCollection,
) -> HistoryDeleteResult:
    """
    Hard-delete a conversation and all its associated records:
      - messages
      - intent_logs
      - sentiment_logs
    The conversation document itself is also deleted.
    """
    # Delete all sub-documents concurrently
    msg_res, intent_res, sent_res = await asyncio.gather(
        messages_col.delete_many({"conversation_id": conversation_id}),
        intent_logs_col.delete_many({"conversation_id": conversation_id}),
        sentiment_logs_col.delete_many({"conversation_id": conversation_id}),
    )

    # Delete the conversation document
    await conversations_col.delete_one({"conversation_id": conversation_id})

    logger.info(
        "Conversation history deleted | conv=%s msgs=%d intents=%d sentiments=%d",
        conversation_id,
        msg_res.deleted_count,
        intent_res.deleted_count,
        sent_res.deleted_count,
    )

    return HistoryDeleteResult(
        conversation_id=conversation_id,
        deleted_messages=msg_res.deleted_count,
        deleted_sentiment=sent_res.deleted_count,
        deleted_intent=intent_res.deleted_count,
    )


# ── Search messages across conversations ─────────────────────

async def search_messages(
    messages_col: AsyncIOMotorCollection,
    query_text:   str,
    user_id:      Optional[str] = None,
    role:         Optional[str] = None,
    skip:         int           = 0,
    limit:        int           = 20,
) -> tuple[list[dict], int]:
    """Full-text search inside message content."""
    q: dict = {"content": {"$regex": query_text, "$options": "i"}}
    if role: q["role"] = role

    total  = await messages_col.count_documents(q)
    cursor = (
        messages_col.find(q)
        .sort("created_at", DESCENDING)
        .skip(skip)
        .limit(limit)
    )
    docs = await cursor.to_list(length=limit)
    for d in docs:
        d["_id"] = str(d["_id"])
    return docs, total
