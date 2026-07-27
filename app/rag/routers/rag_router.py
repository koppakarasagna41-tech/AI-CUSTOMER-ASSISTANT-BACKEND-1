"""
app/rag/routers/rag_router.py
──────────────────────────────
RAG (Retrieval-Augmented Generation) API endpoints.

POST /api/v1/rag/query
    Full RAG query with conversation persistence and escalation support.
    Creates or continues a conversation. Returns AI answer + sources,
    or an escalation message if confidence is below threshold.

POST /api/v1/rag/ask
    Single-shot question — no conversation history or persistence.
    Useful for quick lookups, testing, or stateless integrations.

GET  /api/v1/rag/history/{conversation_id}
    Retrieve the full message history of a RAG conversation.

DELETE /api/v1/rag/history/{conversation_id}
    Delete all messages of a RAG conversation.

All endpoints require a valid Bearer token.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from motor.motor_asyncio import AsyncIOMotorCollection
from pymongo import ASCENDING

from app.core.auth_deps    import get_current_user
from app.core.exceptions   import BadRequestError, NotFoundError
from app.core.responses    import success_response, paginated_response
from app.database.dependencies import (
    ConversationsCollection,
    MessagesCollection,
    get_col,
)
from app.rag.schemas.request   import QueryRequest, AskRequest
from app.rag.schemas.response  import (
    RAGResponse, EscalationResponse,
    HistoryMessageOut, ConversationHistoryOut,
    SourceChunk,
)
from app.rag.services.rag_service import run_rag_pipeline, run_ask_pipeline

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/rag", tags=["RAG — AI Q&A"])

# Pre-built collection dependencies for RAG-specific collections
RetrievalLogsCollection = get_col("retrieval_logs")
EscalationsCollection   = get_col("escalations")


# ── POST /rag/query ───────────────────────────────────────────

@router.post(
    "/query",
    summary="RAG query — full pipeline with conversation persistence",
)
async def rag_query(
    payload:           QueryRequest,
    current_user:      dict                   = Depends(get_current_user),
    conversations_col: AsyncIOMotorCollection = Depends(ConversationsCollection),
    messages_col:      AsyncIOMotorCollection = Depends(MessagesCollection),
    logs_col:          AsyncIOMotorCollection = Depends(RetrievalLogsCollection),
    escalations_col:   AsyncIOMotorCollection = Depends(EscalationsCollection),
):
    """
    Execute the full RAG pipeline:
    1. Embed the question
    2. Search ChromaDB
    3. Evaluate confidence
    4. Generate answer (or escalate)
    5. Persist conversation + retrieval log
    6. Return structured response
    """
    result = await run_rag_pipeline(
        question=payload.question,
        conversation_id=payload.conversation_id,
        user_id=current_user.get("_id"),
        top_k=payload.top_k,
        conversations_col=conversations_col,
        messages_col=messages_col,
        logs_col=logs_col,
        escalations_col=escalations_col,
    )

    if result.escalated:
        data = EscalationResponse(
            conversation_id=result.conversation_id,
            question=result.question,
            answer=result.answer,
            confidence_score=result.confidence_score,
            escalated=True,
            escalation_id=result.escalation_id,
            response_time_ms=result.response_time_ms,
            log_id=result.log_id,
        ).model_dump()
        return success_response(
            data=data,
            message="Your question has been escalated to a human support agent.",
        )

    sources = [
        SourceChunk(
            chunk_id=s["chunk_id"],
            document_id=s["document_id"],
            filename=s["filename"],
            category=s["category"],
            page_number=s.get("page_number"),
            similarity=s["similarity"],
            content_preview=s["content_preview"],
        )
        for s in result.sources
    ]

    data = RAGResponse(
        conversation_id=result.conversation_id,
        question=result.question,
        answer=result.answer,
        confidence_score=result.confidence_score,
        sources=sources,
        tokens_used=result.tokens_used,
        model_used=result.model_used,
        response_time_ms=result.response_time_ms,
        escalated=False,
        log_id=result.log_id,
    ).model_dump()

    return success_response(data=data, message="Answer generated.")


# ── POST /rag/ask ─────────────────────────────────────────────

@router.post(
    "/ask",
    summary="Single-shot RAG question — no persistence",
)
async def rag_ask(
    payload:      AskRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Lightweight RAG — embeds the question, searches ChromaDB,
    and generates an answer without saving any conversation data.
    """
    result = await run_ask_pipeline(
        question=payload.question,
        top_k=payload.top_k,
    )

    if result.escalated:
        data = EscalationResponse(
            conversation_id="",
            question=result.question,
            answer=result.answer,
            confidence_score=result.confidence_score,
            escalated=True,
            response_time_ms=result.response_time_ms,
        ).model_dump()
        return success_response(
            data=data,
            message="Could not find a confident answer. Please contact support.",
        )

    sources = [
        SourceChunk(
            chunk_id=s["chunk_id"],
            document_id=s["document_id"],
            filename=s["filename"],
            category=s["category"],
            page_number=s.get("page_number"),
            similarity=s["similarity"],
            content_preview=s["content_preview"],
        )
        for s in result.sources
    ]

    data = RAGResponse(
        conversation_id="",
        question=result.question,
        answer=result.answer,
        confidence_score=result.confidence_score,
        sources=sources,
        tokens_used=result.tokens_used,
        model_used=result.model_used,
        response_time_ms=result.response_time_ms,
        escalated=False,
    ).model_dump()

    return success_response(data=data, message="Answer generated.")


# ── GET /rag/history/{conversation_id} ────────────────────────

@router.get(
    "/history/{conversation_id}",
    summary="Get RAG conversation message history",
)
async def get_rag_history(
    conversation_id: str,
    page:            int                   = Query(1,   ge=1),
    page_size:       int                   = Query(50,  ge=1, le=200),
    current_user:    dict                  = Depends(get_current_user),
    messages_col:    AsyncIOMotorCollection = Depends(MessagesCollection),
    conversations_col: AsyncIOMotorCollection = Depends(ConversationsCollection),
):
    """Return paginated message history for a RAG conversation."""
    # Verify conversation exists
    conv = await conversations_col.find_one({"conversation_id": conversation_id})
    if not conv:
        raise NotFoundError(
            f"Conversation '{conversation_id}' not found.",
            error_code="CONV_NOT_FOUND",
        )

    # Ownership check — customers can only see their own conversations
    user_id = current_user.get("_id", "")
    role    = current_user.get("role", "customer")
    if role != "admin" and conv.get("user_id") != user_id:
        raise NotFoundError(
            f"Conversation '{conversation_id}' not found.",
            error_code="CONV_NOT_FOUND",
        )

    skip  = (page - 1) * page_size
    total = await messages_col.count_documents(
        {"conversation_id": conversation_id}
    )
    cursor = (
        messages_col
        .find({"conversation_id": conversation_id})
        .sort("created_at", ASCENDING)
        .skip(skip)
        .limit(page_size)
    )
    raw_msgs = await cursor.to_list(length=page_size)

    messages = [
        HistoryMessageOut(
            id=str(m.get("_id", "")),
            role=m.get("role", ""),
            content=m.get("content", ""),
            created_at=m.get("created_at"),
        ).model_dump()
        for m in raw_msgs
    ]

    return paginated_response(
        data=messages,
        total_items=total,
        page=page,
        page_size=page_size,
        message="Conversation history retrieved.",
    )


# ── DELETE /rag/history/{conversation_id} ─────────────────────

@router.delete(
    "/history/{conversation_id}",
    summary="Delete RAG conversation history",
)
async def delete_rag_history(
    conversation_id:   str,
    current_user:      dict                   = Depends(get_current_user),
    conversations_col: AsyncIOMotorCollection = Depends(ConversationsCollection),
    messages_col:      AsyncIOMotorCollection = Depends(MessagesCollection),
):
    """Delete all messages of a RAG conversation. Admin or owner only."""
    conv = await conversations_col.find_one({"conversation_id": conversation_id})
    if not conv:
        raise NotFoundError(
            f"Conversation '{conversation_id}' not found.",
            error_code="CONV_NOT_FOUND",
        )

    user_id = current_user.get("_id", "")
    role    = current_user.get("role", "customer")
    if role != "admin" and conv.get("user_id") != user_id:
        raise NotFoundError(
            f"Conversation '{conversation_id}' not found.",
            error_code="CONV_NOT_FOUND",
        )

    # Delete messages
    result = await messages_col.delete_many(
        {"conversation_id": conversation_id}
    )
    # Delete conversation record
    await conversations_col.delete_one(
        {"conversation_id": conversation_id}
    )

    return success_response(
        data={
            "conversation_id": conversation_id,
            "deleted_messages": result.deleted_count,
        },
        message="Conversation history deleted.",
    )
