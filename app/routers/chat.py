"""
app/routers/chat.py
────────────────────
AI Chat endpoints powered by Google Gemini.

POST /api/v1/chat
    Start a brand-new conversation and send the first message.
    Creates the conversation document, then triggers the Gemini response.

POST /api/v1/chat/{conversation_id}
    Send a follow-up message to an existing conversation.

GET  /api/v1/chat/{conversation_id}/history
    Retrieve the full message history of a conversation.

All endpoints require a valid Bearer token (any authenticated user).
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from motor.motor_asyncio import AsyncIOMotorCollection
from pymongo import ASCENDING

from app.core.auth_deps  import get_current_user
from app.core.exceptions import BadRequestError, NotFoundError
from app.core.responses  import success_response, paginated_response
from app.database        import (
    ConversationsCollection,
    MessagesCollection,
    create_document,
    get_document,
    get_document_by_id,
    get_documents,
    count_documents,
)
from app.schemas.chat    import ChatRequest, ChatResponse, MessageOut, StartChatRequest
from app.services.gemini import GeminiService, GeminiResult
from app.config import settings
from app.utils.helpers   import generate_conversation_id, utc_now

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["AI Chat"])


# ── Helpers ───────────────────────────────────────────────────

def _result_to_response(
    result:    GeminiResult,
    user_msg_id: str,
    user_msg_content: str,
    user_msg_created: datetime,
    ai_msg_created:   datetime,
) -> ChatResponse:
    return ChatResponse(
        conversation_id=result.conversation_id,
        user_message=MessageOut(
            id=result.user_message_id,
            conversation_id=result.conversation_id,
            role="user",
            content=user_msg_content,
            created_at=user_msg_created,
        ),
        ai_response=MessageOut(
            id=result.ai_message_id,
            conversation_id=result.conversation_id,
            role="assistant",
            content=result.ai_content,
            tokens_used=result.tokens_used,
            model_used=result.model_used,
            is_fallback=result.is_fallback,
            created_at=ai_msg_created,
        ),
        tokens_used=result.tokens_used,
        model_used=result.model_used,
        is_fallback=result.is_fallback,
    )


# ── Endpoints ─────────────────────────────────────────────────

@router.post(
    "",
    status_code=201,
    summary="Start a new conversation and send first message",
)
async def start_chat(
    payload:           StartChatRequest,
    current_user:      dict                  = Depends(get_current_user),
    conv_col:          AsyncIOMotorCollection = Depends(ConversationsCollection),
    msg_col:           AsyncIOMotorCollection = Depends(MessagesCollection),
):
    """
    Creates a new conversation and immediately processes the first message
    through Gemini.  Returns the AI's first response.
    """
    if not any([
        settings.GEMINI_API_KEY and not settings.GEMINI_API_KEY.startswith("your-"),
        settings.OPENAI_API_KEY,
        settings.GROQ_API_KEY,
        settings.DEEPSEEK_API_KEY,
    ]):
        raise BadRequestError(
            message="AI service is not configured. Set GEMINI_API_KEY, OPENAI_API_KEY, GROQ_API_KEY, or DEEPSEEK_API_KEY in your environment.",
            error_code="AI_NOT_CONFIGURED",
        )

    now             = utc_now()
    conversation_id = generate_conversation_id()
    user_id         = current_user.get("_id", "")
    user_name       = current_user.get("full_name")

    # Determine title: use provided, or auto-generate later
    title = payload.title or payload.message[:60]

    # Create the conversation document
    conv_doc = {
        "conversation_id": conversation_id,
        "user_id":         user_id,
        "title":           title,
        "status":          "open",
        "message_count":   0,
        "last_message_at": None,
        "tags":            [],
        "metadata":        {},
        "created_at":      now,
        "updated_at":      now,
    }
    await create_document(conv_col, conv_doc)

    before = utc_now()

    # Call Gemini
    result = await GeminiService.chat(
        conversation_id=conversation_id,
        user_message=payload.message,
        conversations_col=conv_col,
        messages_col=msg_col,
        user_name=user_name,
    )

    after = utc_now()

    logger.info(
        "New chat started | user=%s conversation=%s tokens=%d fallback=%s",
        user_id, conversation_id, result.tokens_used, result.is_fallback,
    )

    response = _result_to_response(
        result=result,
        user_msg_id=result.user_message_id,
        user_msg_content=payload.message,
        user_msg_created=before,
        ai_msg_created=after,
    )

    return success_response(
        data=response.model_dump(),
        message="Conversation started." if not result.is_fallback else
                "Conversation started (AI encountered an issue).",
    )


@router.post(
    "/{conversation_id}",
    summary="Send a message to an existing conversation",
)
async def send_message(
    conversation_id: str,
    payload:         ChatRequest,
    current_user:    dict                  = Depends(get_current_user),
    conv_col:        AsyncIOMotorCollection = Depends(ConversationsCollection),
    msg_col:         AsyncIOMotorCollection = Depends(MessagesCollection),
):
    """
    Send a follow-up message to an existing conversation and get the AI reply.
    The conversation must belong to the authenticated user.
    """
    if not any([
        settings.GEMINI_API_KEY and not settings.GEMINI_API_KEY.startswith("your-"),
        settings.OPENAI_API_KEY,
        settings.GROQ_API_KEY,
        settings.DEEPSEEK_API_KEY,
    ]):
        raise BadRequestError(
            message="AI service is not configured. Set GEMINI_API_KEY, OPENAI_API_KEY, GROQ_API_KEY, or DEEPSEEK_API_KEY in your environment.",
            error_code="AI_NOT_CONFIGURED",
        )

    # Verify conversation exists
    conversation = await get_document(
        conv_col, {"conversation_id": conversation_id}
    )
    if not conversation:
        raise NotFoundError(
            "Conversation not found.",
            error_code="CONV_NOT_FOUND",
        )

    # Optionally enforce ownership (customers can only access their own convs)
    user_id = current_user.get("_id", "")
    role    = current_user.get("role", "customer")
    if role != "admin" and conversation.get("user_id") != user_id:
        raise NotFoundError(
            "Conversation not found.",
            error_code="CONV_NOT_FOUND",
        )

    before = utc_now()

    result = await GeminiService.chat(
        conversation_id=conversation_id,
        user_message=payload.message,
        conversations_col=conv_col,
        messages_col=msg_col,
        user_name=current_user.get("full_name"),
    )

    after = utc_now()

    logger.info(
        "Chat message | user=%s conversation=%s tokens=%d fallback=%s",
        user_id, conversation_id, result.tokens_used, result.is_fallback,
    )

    response = _result_to_response(
        result=result,
        user_msg_id=result.user_message_id,
        user_msg_content=payload.message,
        user_msg_created=before,
        ai_msg_created=after,
    )

    return success_response(
        data=response.model_dump(),
        message="Response generated." if not result.is_fallback else
                "Response generated (AI encountered an issue).",
    )


@router.get(
    "/{conversation_id}/history",
    summary="Get conversation message history",
)
async def get_history(
    conversation_id: str,
    page:            int                  = Query(1,   ge=1),
    page_size:       int                  = Query(50,  ge=1, le=200),
    current_user:    dict                  = Depends(get_current_user),
    conv_col:        AsyncIOMotorCollection = Depends(ConversationsCollection),
    msg_col:         AsyncIOMotorCollection = Depends(MessagesCollection),
):
    """
    Return paginated message history for a conversation (oldest → newest).
    """
    conversation = await get_document(
        conv_col, {"conversation_id": conversation_id}
    )
    if not conversation:
        raise NotFoundError("Conversation not found.", error_code="CONV_NOT_FOUND")

    # Ownership check
    user_id = current_user.get("_id", "")
    if current_user.get("role") != "admin" and conversation.get("user_id") != user_id:
        raise NotFoundError("Conversation not found.", error_code="CONV_NOT_FOUND")

    q     = {"conversation_id": conversation_id}
    skip  = (page - 1) * page_size
    total = await count_documents(msg_col, q)
    docs  = await get_documents(
        msg_col,
        filter_query=q,
        skip=skip,
        limit=page_size,
        sort=[("created_at", ASCENDING)],
    )

    items = [
        MessageOut(
            id=d["_id"],
            conversation_id=d["conversation_id"],
            role=d["role"],
            content=d["content"],
            tokens_used=d.get("tokens_used"),
            model_used=d.get("model_used"),
            is_fallback=d.get("metadata", {}).get("is_fallback", False),
            created_at=d.get("created_at"),
        ).model_dump()
        for d in docs
    ]

    return paginated_response(
        data=items,
        total_items=total,
        page=page,
        page_size=page_size,
        message="History retrieved.",
    )
