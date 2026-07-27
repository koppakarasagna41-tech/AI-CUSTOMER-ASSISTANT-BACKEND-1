"""
app/history/routers/history_router.py
───────────────────────────────────────
Conversation History API.

GET  /history
    List conversation history summaries.
    Supports: search, filter (status, sentiment, user, date range, has_tickets),
              sort (created_at, updated_at, message_count, sentiment_polarity),
              pagination.

GET  /history/search
    Full-text search across message content.

GET  /history/{conversation_id}
    Full enriched conversation history with all messages,
    per-message intent, per-message sentiment, and linked tickets.
    Supports pagination over messages.

DELETE /history/{conversation_id}
    Hard-delete a conversation + all messages + intent logs + sentiment logs.
    Admin only.

DELETE /history/{conversation_id}/messages
    Delete only the messages of a conversation (keep the conversation record).
    Admin only.
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from motor.motor_asyncio import AsyncIOMotorCollection
from pymongo import ASCENDING

from app.core.auth_deps  import get_current_user, require_admin
from app.core.exceptions import NotFoundError
from app.core.responses  import success_response, paginated_response
from app.database        import (
    ConversationsCollection,
    MessagesCollection,
    IntentLogsCollection,
    SentimentLogsCollection,
    TicketsCollection,
)
from app.history.schemas import (
    ConversationHistory,
    ConversationHistoryList,
    HistoryDeleteResult,
    MessageHistoryItem,
    MessageIntentOut,
    MessageSentimentOut,
)
from app.history.services import (
    get_conversation_history,
    list_conversation_history,
    delete_conversation_history,
    search_messages,
)
from app.schemas.message import MessageOut
from app.sentiment.constants import SENTIMENT_META

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/history", tags=["Conversation History"])


# ── GET /history ──────────────────────────────────────────────

@router.get(
    "",
    summary="List conversation history with filtering, sorting, and pagination",
)
async def list_history(
    # Pagination
    page:      int = Query(1,  ge=1),
    page_size: int = Query(20, ge=1, le=100),

    # Filters
    search:      Optional[str]      = Query(None, description="Search title, tags, conversation_id"),
    status:      Optional[str]      = Query(None, description="open | pending | resolved | closed"),
    sentiment:   Optional[str]      = Query(None, description="positive | neutral | negative | very_negative"),
    has_tickets: Optional[bool]     = Query(None, description="Filter conversations that have linked tickets"),
    date_from:   Optional[datetime] = Query(None, description="Created after (ISO format)"),
    date_to:     Optional[datetime] = Query(None, description="Created before (ISO format)"),

    # Sorting
    sort_by:    str = Query("created_at",  description="created_at | updated_at | message_count | sentiment_polarity"),
    sort_order: str = Query("desc",        description="asc | desc"),

    current_user:       dict                   = Depends(get_current_user),
    conversations_col:  AsyncIOMotorCollection = Depends(ConversationsCollection),
    tickets_col:        AsyncIOMotorCollection = Depends(TicketsCollection),
):
    """
    Returns paginated conversation summaries.
    Admins see all conversations; customers see only their own.
    """
    role    = current_user.get("role", "customer")
    user_id = current_user.get("_id") if role != "admin" else None

    skip        = (page - 1) * page_size
    items, total = await list_conversation_history(
        conversations_col=conversations_col,
        tickets_col=tickets_col,
        skip=skip,
        limit=page_size,
        user_id=user_id,
        status=status,
        sentiment=sentiment,
        has_tickets=has_tickets,
        search=search,
        date_from=date_from,
        date_to=date_to,
        sort_by=sort_by,
        sort_order=sort_order,
    )

    return paginated_response(
        data=[i.model_dump() for i in items],
        total_items=total,
        page=page,
        page_size=page_size,
        message=f"{total} conversation(s) found.",
    )


# ── GET /history/search ───────────────────────────────────────

@router.get(
    "/search",
    summary="Full-text search inside message content",
)
async def search_message_content(
    q:         str           = Query(..., min_length=2, description="Text to search in messages"),
    role:      Optional[str] = Query(None, description="user | assistant | system"),
    page:      int           = Query(1,    ge=1),
    page_size: int           = Query(20,   ge=1, le=100),

    current_user:  dict                   = Depends(get_current_user),
    messages_col:  AsyncIOMotorCollection = Depends(MessagesCollection),
):
    """
    Search message content across all conversations the user has access to.
    Returns matched messages with conversation_id for easy lookup.
    """
    skip        = (page - 1) * page_size
    docs, total = await search_messages(
        messages_col=messages_col,
        query_text=q,
        role=role,
        skip=skip,
        limit=page_size,
    )

    items = [MessageOut(**{**d, "id": d["_id"]}).model_dump() for d in docs]

    return paginated_response(
        data=items,
        total_items=total,
        page=page,
        page_size=page_size,
        message=f"{total} message(s) matching '{q}'.",
    )


# ── GET /history/{conversation_id} ───────────────────────────

@router.get(
    "/{conversation_id}",
    summary="Get full enriched history of a conversation",
)
async def get_history(
    conversation_id: str,

    # Message pagination
    msg_page:      int = Query(1,  ge=1, description="Page number for messages"),
    msg_page_size: int = Query(50, ge=1, le=200, description="Messages per page"),

    current_user:        dict                   = Depends(get_current_user),
    conversations_col:   AsyncIOMotorCollection = Depends(ConversationsCollection),
    messages_col:        AsyncIOMotorCollection = Depends(MessagesCollection),
    intent_logs_col:     AsyncIOMotorCollection = Depends(IntentLogsCollection),
    sentiment_logs_col:  AsyncIOMotorCollection = Depends(SentimentLogsCollection),
    tickets_col:         AsyncIOMotorCollection = Depends(TicketsCollection),
):
    """
    Returns the full conversation history including:
    - All messages (paginated) with role, content, timestamp
    - Per-message intent label + confidence
    - Per-message sentiment label + polarity + emoji
    - Conversation-level sentiment summary + trend
    - Linked support tickets
    """
    history = await get_conversation_history(
        conversation_id=conversation_id,
        conversations_col=conversations_col,
        messages_col=messages_col,
        intent_logs_col=intent_logs_col,
        sentiment_logs_col=sentiment_logs_col,
        tickets_col=tickets_col,
        msg_page=msg_page,
        msg_page_size=msg_page_size,
    )

    if not history:
        raise NotFoundError(
            f"Conversation '{conversation_id}' not found.",
            error_code="CONV_NOT_FOUND",
        )

    # Ownership check — customers only see their own conversations
    role    = current_user.get("role", "customer")
    user_id = current_user.get("_id")
    if role != "admin" and history.user_id and history.user_id != user_id:
        raise NotFoundError(
            f"Conversation '{conversation_id}' not found.",
            error_code="CONV_NOT_FOUND",
        )

    return success_response(
        data=history.model_dump(),
        message=(
            f"History retrieved — {history.messages_total} messages"
            + (f", sentiment: {history.sentiment_summary.dominant}" if history.sentiment_summary else "")
            + (f", {len(history.linked_tickets)} ticket(s)" if history.linked_tickets else "")
            + "."
        ),
    )


# ── DELETE /history/{conversation_id} ────────────────────────

@router.delete(
    "/{conversation_id}",
    summary="Hard-delete a conversation and ALL its associated data [admin]",
)
async def delete_history(
    conversation_id:     str,
    _:                   dict                   = Depends(require_admin),
    conversations_col:   AsyncIOMotorCollection = Depends(ConversationsCollection),
    messages_col:        AsyncIOMotorCollection = Depends(MessagesCollection),
    intent_logs_col:     AsyncIOMotorCollection = Depends(IntentLogsCollection),
    sentiment_logs_col:  AsyncIOMotorCollection = Depends(SentimentLogsCollection),
):
    """
    Permanently deletes:
    - The conversation document
    - All messages in the conversation
    - All intent logs linked to the conversation
    - All sentiment logs linked to the conversation
    """
    conv = await conversations_col.find_one({"conversation_id": conversation_id})
    if not conv:
        raise NotFoundError(
            f"Conversation '{conversation_id}' not found.",
            error_code="CONV_NOT_FOUND",
        )

    result = await delete_conversation_history(
        conversation_id=conversation_id,
        conversations_col=conversations_col,
        messages_col=messages_col,
        intent_logs_col=intent_logs_col,
        sentiment_logs_col=sentiment_logs_col,
    )

    return success_response(
        data=result.model_dump(),
        message=(
            f"Conversation {conversation_id} deleted — "
            f"{result.deleted_messages} message(s), "
            f"{result.deleted_intent} intent log(s), "
            f"{result.deleted_sentiment} sentiment log(s) removed."
        ),
    )


# ── DELETE /history/{conversation_id}/messages ────────────────

@router.delete(
    "/{conversation_id}/messages",
    summary="Delete only the messages of a conversation (keep conversation record) [admin]",
)
async def delete_messages_only(
    conversation_id: str,
    _:               dict                   = Depends(require_admin),
    conversations_col: AsyncIOMotorCollection = Depends(ConversationsCollection),
    messages_col:    AsyncIOMotorCollection = Depends(MessagesCollection),
):
    """Clears all messages from a conversation without deleting the conversation itself."""
    conv = await conversations_col.find_one({"conversation_id": conversation_id})
    if not conv:
        raise NotFoundError(
            f"Conversation '{conversation_id}' not found.",
            error_code="CONV_NOT_FOUND",
        )

    result = await messages_col.delete_many({"conversation_id": conversation_id})

    # Reset message_count on the conversation
    from app.utils.helpers import utc_now
    await conversations_col.update_one(
        {"conversation_id": conversation_id},
        {"$set": {"message_count": 0, "last_message_at": None, "updated_at": utc_now()}},
    )

    logger.info(
        "Messages cleared | conv=%s count=%d",
        conversation_id, result.deleted_count,
    )

    return success_response(
        data={"conversation_id": conversation_id, "deleted_messages": result.deleted_count},
        message=f"{result.deleted_count} message(s) deleted from conversation {conversation_id}.",
    )
