"""
app/rag/services/rag_service.py
────────────────────────────────
RAG Pipeline Orchestrator — the single entry point for all RAG queries.

Full pipeline:
  1.  Validate inputs
  2.  Generate query embedding            (Gemini Embedding API)
  3.  Similarity search                   (ChromaDB)
  4.  Calculate confidence score
  5a. HIGH confidence → build prompt → call Gemini → return answer + sources
  5b. LOW confidence  → create escalation record → return escalation message
  6.  Persist conversation + messages     (MongoDB)
  7.  Persist retrieval log               (MongoDB)
  8.  Return structured result
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorCollection

from app.config  import settings
from app.utils.helpers import utc_now

from app.rag.embeddings.query_embedder      import embed_query
from app.rag.retrieval.similarity_search    import similarity_search, RetrievedChunk
from app.rag.confidence.scorer              import calculate_confidence
from app.rag.llm.gemini_rag                 import generate_rag_answer
from app.rag.escalation.escalation_service  import create_escalation
from app.rag.utils.helpers                  import (
    generate_log_id,
    generate_rag_conversation_id,
    truncate_preview,
)
from app.knowledge.embeddings.embedding_service import (
    is_embedding_configured, EmbeddingError,
)

logger = logging.getLogger(__name__)


# ── Result dataclass ──────────────────────────────────────────

@dataclass
class RAGPipelineResult:
    """Unified result object returned to the router."""
    conversation_id:  str
    question:         str
    answer:           str
    confidence_score: float
    is_confident:     bool
    escalated:        bool
    escalation_id:    Optional[str]
    sources:          list[dict]          = field(default_factory=list)
    tokens_used:      int                 = 0
    model_used:       str                 = ""
    response_time_ms: float               = 0.0
    log_id:           Optional[str]       = None


# ── Pipeline ──────────────────────────────────────────────────

async def run_rag_pipeline(
    *,
    question:         str,
    conversation_id:  Optional[str],
    user_id:          Optional[str],
    top_k:            Optional[int],
    conversations_col: AsyncIOMotorCollection,
    messages_col:      AsyncIOMotorCollection,
    logs_col:          AsyncIOMotorCollection,
    escalations_col:   AsyncIOMotorCollection,
) -> RAGPipelineResult:
    """
    Execute the full RAG pipeline and return a structured result.
    Never raises — all errors are captured into the result.
    """
    start_ms   = time.perf_counter()
    k          = top_k or settings.RAG_TOP_K
    conv_id    = conversation_id or generate_rag_conversation_id()
    log_id     = generate_log_id()
    now        = utc_now()

    # ── Guard: embedding must be configured ───────────────────
    if not is_embedding_configured():
        return RAGPipelineResult(
            conversation_id=conv_id,
            question=question,
            answer=(
                "The AI service is not fully configured. "
                "Please contact your administrator."
            ),
            confidence_score=0.0,
            is_confident=False,
            escalated=False,
            escalation_id=None,
            response_time_ms=_elapsed(start_ms),
            log_id=log_id,
        )

    # ── Step 1: Embed the query ───────────────────────────────
    try:
        logger.info("RAG query start | conversation_id=%s question=%s top_k=%d", conv_id, question, k)
        query_vector = await embed_query(question)
        logger.info("Query embedding generated | conversation_id=%s dims=%d", conv_id, len(query_vector))
    except EmbeddingError as exc:
        logger.error("Query embedding failed: %s", exc.message)
        return RAGPipelineResult(
            conversation_id=conv_id,
            question=question,
            answer=settings.RAG_ESCALATION_MESSAGE,
            confidence_score=0.0,
            is_confident=False,
            escalated=True,
            escalation_id=await create_escalation(
                escalations_col, conv_id, question, 0.0,
                reason="embedding_failure", user_id=user_id, log_id=log_id,
            ),
            response_time_ms=_elapsed(start_ms),
            log_id=log_id,
        )

    # ── Step 2: Similarity search ─────────────────────────────
    chunks: list[RetrievedChunk] = await similarity_search(
        query_vector=query_vector,
        top_k=k,
    )
    logger.info("Retrieval complete | conversation_id=%s chunk_count=%d", conv_id, len(chunks))

    # ── Step 3: Confidence score ──────────────────────────────
    conf = calculate_confidence(chunks=chunks, top_k=k)

    # ── Step 4a: LOW confidence → escalate ───────────────────
    if not conf.is_confident:
        esc_id = await create_escalation(
            escalations_col,
            conv_id,
            question,
            confidence_score=conf.score,
            reason="low_confidence",
            user_id=user_id,
            log_id=log_id,
        )

        await _save_conversation_turn(
            conversations_col=conversations_col,
            messages_col=messages_col,
            conv_id=conv_id,
            user_id=user_id,
            question=question,
            answer=settings.RAG_ESCALATION_MESSAGE,
            now=now,
        )

        await _save_retrieval_log(
            logs_col=logs_col,
            log_id=log_id,
            conv_id=conv_id,
            user_id=user_id,
            question=question,
            chunks=chunks,
            ai_response=settings.RAG_ESCALATION_MESSAGE,
            conf_score=conf.score,
            tokens=0,
            model=settings.GEMINI_MODEL,
            elapsed_ms=_elapsed(start_ms),
            escalation_id=esc_id,
            escalated=True,
        )

        return RAGPipelineResult(
            conversation_id=conv_id,
            question=question,
            answer=settings.RAG_ESCALATION_MESSAGE,
            confidence_score=conf.score,
            is_confident=False,
            escalated=True,
            escalation_id=esc_id,
            sources=[],
            response_time_ms=_elapsed(start_ms),
            log_id=log_id,
        )

    # ── Step 4b: HIGH confidence → generate answer ───────────
    logger.info("Generating RAG answer | conversation_id=%s chunk_count=%d", conv_id, len(chunks))
    llm_result = await generate_rag_answer(question=question, chunks=chunks)
    logger.info(
        "LLM response generated | conversation_id=%s provider=%s tokens=%d answer_preview=%s",
        conv_id, llm_result.model_used, llm_result.tokens_used, (llm_result.answer[:180] if llm_result.answer else "")
    )

    # Build source list for response
    sources = [
        {
            "chunk_id":       c.chunk_id,
            "document_id":    c.document_id,
            "filename":       c.filename,
            "category":       c.category,
            "page_number":    c.page_number,
            "similarity":     c.similarity,
            "content_preview": truncate_preview(c.content, 200),
        }
        for c in chunks
    ]

    elapsed = _elapsed(start_ms)

    await _save_conversation_turn(
        conversations_col=conversations_col,
        messages_col=messages_col,
        conv_id=conv_id,
        user_id=user_id,
        question=question,
        answer=llm_result.answer,
        now=now,
    )

    await _save_retrieval_log(
        logs_col=logs_col,
        log_id=log_id,
        conv_id=conv_id,
        user_id=user_id,
        question=question,
        chunks=chunks,
        ai_response=llm_result.answer,
        conf_score=conf.score,
        tokens=llm_result.tokens_used,
        model=llm_result.model_used,
        elapsed_ms=elapsed,
        escalation_id=None,
        escalated=False,
    )

    return RAGPipelineResult(
        conversation_id=conv_id,
        question=question,
        answer=llm_result.answer,
        confidence_score=conf.score,
        is_confident=True,
        escalated=False,
        escalation_id=None,
        sources=sources,
        tokens_used=llm_result.tokens_used,
        model_used=llm_result.model_used,
        response_time_ms=elapsed,
        log_id=log_id,
    )


# ── Single-shot pipeline (no persistence) ────────────────────

async def run_ask_pipeline(
    *,
    question:       str,
    top_k:          Optional[int],
) -> RAGPipelineResult:
    """
    Lightweight single-shot RAG — no conversation or log persistence.
    Used by POST /rag/ask.
    """
    start_ms = time.perf_counter()
    k        = top_k or settings.RAG_TOP_K

    if not is_embedding_configured():
        return RAGPipelineResult(
            conversation_id="",
            question=question,
            answer="The AI service is not configured.",
            confidence_score=0.0,
            is_confident=False,
            escalated=False,
            escalation_id=None,
            response_time_ms=_elapsed(start_ms),
        )

    try:
        query_vector = await embed_query(question)
    except EmbeddingError:
        return RAGPipelineResult(
            conversation_id="",
            question=question,
            answer=settings.RAG_ESCALATION_MESSAGE,
            confidence_score=0.0,
            is_confident=False,
            escalated=True,
            escalation_id=None,
            response_time_ms=_elapsed(start_ms),
        )

    chunks = await similarity_search(query_vector=query_vector, top_k=k)
    conf   = calculate_confidence(chunks=chunks, top_k=k)

    if not conf.is_confident:
        return RAGPipelineResult(
            conversation_id="",
            question=question,
            answer=settings.RAG_ESCALATION_MESSAGE,
            confidence_score=conf.score,
            is_confident=False,
            escalated=True,
            escalation_id=None,
            response_time_ms=_elapsed(start_ms),
        )

    logger.info("Generating single-shot RAG answer | question=%s chunk_count=%d", question, len(chunks))
    llm = await generate_rag_answer(question=question, chunks=chunks)
    logger.info(
        "Single-shot LLM response | provider=%s tokens=%d answer_preview=%s",
        llm.model_used, llm.tokens_used, (llm.answer[:180] if llm.answer else "")
    )
    sources = [
        {
            "chunk_id":       c.chunk_id,
            "document_id":    c.document_id,
            "filename":       c.filename,
            "category":       c.category,
            "page_number":    c.page_number,
            "similarity":     c.similarity,
            "content_preview": truncate_preview(c.content, 200),
        }
        for c in chunks
    ]

    return RAGPipelineResult(
        conversation_id="",
        question=question,
        answer=llm.answer,
        confidence_score=conf.score,
        is_confident=True,
        escalated=False,
        escalation_id=None,
        sources=sources,
        tokens_used=llm.tokens_used,
        model_used=llm.model_used,
        response_time_ms=_elapsed(start_ms),
    )


# ── Private helpers ───────────────────────────────────────────

def _elapsed(start: float) -> float:
    import time
    return round((time.perf_counter() - start) * 1000, 2)


async def _save_conversation_turn(
    *,
    conversations_col: AsyncIOMotorCollection,
    messages_col:      AsyncIOMotorCollection,
    conv_id:           str,
    user_id:           Optional[str],
    question:          str,
    answer:            str,
    now,
) -> None:
    """Upsert conversation record and append both messages."""
    # Upsert conversation
    await conversations_col.update_one(
        {"conversation_id": conv_id},
        {"$set": {
            "conversation_id": conv_id,
            "user_id":         user_id,
            "source":          "rag",
            "updated_at":      now,
        }, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )

    # Insert user message
    await messages_col.insert_one({
        "conversation_id": conv_id,
        "role":            "user",
        "content":         question,
        "created_at":      now,
        "updated_at":      now,
    })

    # Insert AI message
    await messages_col.insert_one({
        "conversation_id": conv_id,
        "role":            "assistant",
        "content":         answer,
        "created_at":      now,
        "updated_at":      now,
    })


async def _save_retrieval_log(
    *,
    logs_col:       AsyncIOMotorCollection,
    log_id:         str,
    conv_id:        str,
    user_id:        Optional[str],
    question:       str,
    chunks:         list[RetrievedChunk],
    ai_response:    str,
    conf_score:     float,
    tokens:         int,
    model:          str,
    elapsed_ms:     float,
    escalation_id:  Optional[str],
    escalated:      bool,
) -> None:
    """Persist a retrieval log entry."""
    sims = [c.similarity for c in chunks]
    now  = utc_now()

    await logs_col.insert_one({
        "log_id":                 log_id,
        "conversation_id":        conv_id,
        "user_id":                user_id,
        "customer_question":      question,
        "query_embedding_dims":   None,
        "retrieved_chunks":       len(chunks),
        "retrieved_document_ids": list({c.document_id for c in chunks}),
        "top_similarity_score":   sims[0] if sims else None,
        "avg_similarity_score":   round(sum(sims) / len(sims), 4) if sims else None,
        "ai_response":            ai_response,
        "confidence_score":       conf_score,
        "model_used":             model,
        "tokens_used":            tokens,
        "response_time_ms":       elapsed_ms,
        "escalation_status":      "escalated" if escalated else "not_escalated",
        "escalation_id":          escalation_id,
        "created_at":             now,
        "updated_at":             now,
    })
