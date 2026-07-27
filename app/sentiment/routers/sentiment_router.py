"""
app/sentiment/routers/sentiment_router.py
───────────────────────────────────────────
Sentiment Analysis API endpoints.

POST  /sentiment/analyze
    Analyse sentiment of a single message. Saves to MongoDB. Returns
    sentiment label, confidence score, polarity score, and all class scores.

POST  /sentiment/analyze/batch
    Analyse up to 20 messages at once concurrently.

POST  /sentiment/conversation/{conversation_id}
    Analyse ALL messages in a conversation, aggregate the results, and
    update the conversation document with dominant sentiment + trend.

GET   /sentiment/conversation/{conversation_id}
    Return the stored sentiment history for a conversation.

GET   /sentiment/logs
    Paginated list of all stored sentiment logs with filters.

GET   /sentiment/logs/{sentiment_id}
    Fetch a single log by its SID-... identifier.

GET   /sentiment/summary
    Aggregated counts per sentiment label.

GET   /sentiment/labels
    List all supported sentiment labels with metadata.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from motor.motor_asyncio import AsyncIOMotorCollection
from pymongo import ASCENDING

from app.core.auth_deps  import get_current_user
from app.core.exceptions import NotFoundError
from app.core.responses  import success_response, paginated_response
from app.database        import (
    SentimentLogsCollection,
    ConversationsCollection,
    MessagesCollection,
)
from app.sentiment.constants import Sentiment, SENTIMENT_META
from app.sentiment.schemas   import (
    SentimentRequest, SentimentResult, SentimentScore,
    SentimentBatchRequest, SentimentBatchResult,
    ConversationSentimentOut, SentimentLogOut,
)
from app.sentiment.services import (
    analyze_sentiment, analyze_conversation_sentiment,
    save_sentiment_log, update_conversation_sentiment,
    get_sentiment_log, list_sentiment_logs,
    get_conversation_sentiment_logs, sentiment_summary,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sentiment", tags=["Sentiment Analysis"])


# ── Helper: AnalysisResult → SentimentResult schema ──────────

def _to_schema(
    result,
    sentiment_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    message_id: Optional[str] = None,
) -> SentimentResult:
    scores = [
        SentimentScore(
            sentiment=k,
            label=SENTIMENT_META.get(k, {}).get("label", k.replace("_", " ").title()),
            score=v,
            emoji=SENTIMENT_META.get(k, {}).get("emoji", ""),
        )
        for k, v in sorted(result.all_scores.items(), key=lambda x: x[1], reverse=True)
    ]
    return SentimentResult(
        text=result.text,
        sentiment=result.sentiment,
        label=result.label,
        emoji=result.emoji,
        confidence=result.confidence,
        polarity_score=result.polarity_score,
        is_confident=result.is_confident,
        all_scores=scores,
        model_used=result.model_used,
        tokens_used=result.tokens_used,
        latency_ms=result.latency_ms,
        sentiment_id=sentiment_id,
        conversation_id=conversation_id,
        message_id=message_id,
    )


# ── POST /sentiment/analyze ───────────────────────────────────

@router.post(
    "/analyze",
    summary="Analyse sentiment of a single message",
)
async def analyze_single(
    payload:      SentimentRequest,
    current_user: dict                   = Depends(get_current_user),
    col:          AsyncIOMotorCollection = Depends(SentimentLogsCollection),
):
    """
    Detect sentiment using Gemini with a keyword-based fallback.

    Returns:
    - `sentiment`      — positive | neutral | negative | very_negative
    - `confidence`     — 0.0–1.0
    - `polarity_score` — numeric polarity (-2.0 to +1.0)
    - `all_scores`     — probability for all 4 classes
    """
    result = await analyze_sentiment(text=payload.text)

    sentiment_id = await save_sentiment_log(
        col=col,
        result=result,
        user_id=current_user.get("_id"),
        conversation_id=payload.conversation_id,
        message_id=payload.message_id,
        source=payload.source,
    )

    schema = _to_schema(
        result,
        sentiment_id=sentiment_id,
        conversation_id=payload.conversation_id,
        message_id=payload.message_id,
    )

    logger.info(
        "Sentiment analysed | id=%s sentiment=%s confidence=%.3f",
        sentiment_id, result.sentiment, result.confidence,
    )

    return success_response(
        data=schema.model_dump(),
        message=f"Sentiment: {result.label} {result.emoji} (confidence {result.confidence:.0%})",
    )


# ── POST /sentiment/analyze/batch ─────────────────────────────

@router.post(
    "/analyze/batch",
    summary="Analyse sentiment of multiple messages (max 20)",
)
async def analyze_batch(
    payload:      SentimentBatchRequest,
    current_user: dict                   = Depends(get_current_user),
    col:          AsyncIOMotorCollection = Depends(SentimentLogsCollection),
):
    """Classify up to 20 texts concurrently. Each result is saved individually."""
    import asyncio

    async def _one(text: str) -> SentimentResult:
        result       = await analyze_sentiment(text=text)
        sentiment_id = await save_sentiment_log(
            col=col,
            result=result,
            user_id=current_user.get("_id"),
            conversation_id=payload.conversation_id,
        )
        return _to_schema(result, sentiment_id=sentiment_id,
                          conversation_id=payload.conversation_id)

    results = await asyncio.gather(*[_one(t) for t in payload.texts])

    # Build summary count
    summary: dict[str, int] = {s: 0 for s in Sentiment.all_values()}
    for r in results:
        summary[r.sentiment] = summary.get(r.sentiment, 0) + 1

    batch = SentimentBatchResult(
        results=list(results),
        total=len(results),
        summary={k: v for k, v in summary.items() if v > 0},
    )

    return success_response(
        data=batch.model_dump(),
        message=f"Analysed {len(results)} messages.",
    )


# ── POST /sentiment/conversation/{conversation_id} ────────────

@router.post(
    "/conversation/{conversation_id}",
    summary="Analyse full conversation sentiment and update the conversation record",
)
async def analyze_conversation(
    conversation_id: str,
    current_user:    dict                   = Depends(get_current_user),
    conv_col:        AsyncIOMotorCollection = Depends(ConversationsCollection),
    msg_col:         AsyncIOMotorCollection = Depends(MessagesCollection),
    sent_col:        AsyncIOMotorCollection = Depends(SentimentLogsCollection),
):
    """
    Fetches all user messages from a conversation, analyses each one,
    aggregates the results, and stamps the conversation document with
    the dominant sentiment and trend.
    """
    # Verify conversation exists
    conv = await conv_col.find_one({"conversation_id": conversation_id})
    if not conv:
        raise NotFoundError(
            f"Conversation '{conversation_id}' not found.",
            error_code="CONV_NOT_FOUND",
        )

    # Ownership check
    role    = current_user.get("role", "customer")
    user_id = current_user.get("_id", "")
    if role != "admin" and conv.get("user_id") != user_id:
        raise NotFoundError(
            f"Conversation '{conversation_id}' not found.",
            error_code="CONV_NOT_FOUND",
        )

    # Fetch only user messages (skip AI assistant messages)
    cursor   = msg_col.find(
        {"conversation_id": conversation_id, "role": "user"},
    ).sort("created_at", ASCENDING)
    messages = await cursor.to_list(length=500)

    if not messages:
        return success_response(
            data=ConversationSentimentOut(
                conversation_id=conversation_id,
                total_messages=0,
                dominant_sentiment=Sentiment.NEUTRAL,
                dominant_label="Neutral",
                dominant_emoji="😐",
                average_polarity=0.0,
                distribution={},
                trend="stable",
            ).model_dump(),
            message="No user messages to analyse.",
        )

    texts = [m["content"] for m in messages]

    # Run full conversation analysis
    agg = await analyze_conversation_sentiment(texts)

    # Save individual logs
    import asyncio
    async def _save_one(msg: dict, result) -> SentimentResult:
        mid = str(msg.get("_id", ""))
        sid = await save_sentiment_log(
            col=sent_col,
            result=result,
            user_id=user_id,
            conversation_id=conversation_id,
            message_id=mid,
            source="message",
        )
        return _to_schema(result, sentiment_id=sid,
                          conversation_id=conversation_id, message_id=mid)

    schemas = await asyncio.gather(
        *[_save_one(msg, res)
          for msg, res in zip(messages, agg["results"])]
    )

    # Update conversation document with aggregate sentiment
    await update_conversation_sentiment(
        conversations_col=conv_col,
        conversation_id=conversation_id,
        dominant_sentiment=agg["dominant_sentiment"],
        average_polarity=agg["average_polarity"],
        trend=agg["trend"],
    )

    out = ConversationSentimentOut(
        conversation_id=conversation_id,
        total_messages=len(messages),
        dominant_sentiment=agg["dominant_sentiment"],
        dominant_label=agg["dominant_label"],
        dominant_emoji=agg["dominant_emoji"],
        average_polarity=agg["average_polarity"],
        distribution=agg["distribution"],
        trend=agg["trend"],
        messages=list(schemas),
    )

    logger.info(
        "Conversation sentiment | conv=%s dominant=%s polarity=%.3f trend=%s",
        conversation_id,
        agg["dominant_sentiment"],
        agg["average_polarity"],
        agg["trend"],
    )

    return success_response(
        data=out.model_dump(),
        message=(
            f"Conversation sentiment: {agg['dominant_label']} "
            f"{agg['dominant_emoji']} | Trend: {agg['trend']}"
        ),
    )


# ── GET /sentiment/conversation/{conversation_id} ─────────────

@router.get(
    "/conversation/{conversation_id}",
    summary="Get stored sentiment history for a conversation",
)
async def get_conversation_history(
    conversation_id: str,
    current_user:    dict                   = Depends(get_current_user),
    sent_col:        AsyncIOMotorCollection = Depends(SentimentLogsCollection),
):
    docs  = await get_conversation_sentiment_logs(sent_col, conversation_id)
    items = [SentimentLogOut(**{**d, "id": d["_id"]}).model_dump() for d in docs]
    return success_response(
        data=items,
        message=f"{len(items)} sentiment record(s) for conversation.",
    )


# ── GET /sentiment/logs ───────────────────────────────────────

@router.get(
    "/logs",
    summary="List stored sentiment logs with optional filters",
)
async def list_logs(
    page:            int           = Query(1,    ge=1),
    page_size:       int           = Query(20,   ge=1, le=100),
    sentiment:       Optional[str] = Query(None),
    conversation_id: Optional[str] = Query(None),
    is_fallback:     Optional[bool] = Query(None),
    current_user:    dict                   = Depends(get_current_user),
    col:             AsyncIOMotorCollection = Depends(SentimentLogsCollection),
):
    role    = current_user.get("role", "customer")
    user_id = current_user.get("_id") if role != "admin" else None

    skip        = (page - 1) * page_size
    docs, total = await list_sentiment_logs(
        col=col, skip=skip, limit=page_size,
        sentiment=sentiment,
        conversation_id=conversation_id,
        user_id=user_id,
        is_fallback=is_fallback,
    )
    items = [SentimentLogOut(**{**d, "id": d["_id"]}).model_dump() for d in docs]
    return paginated_response(
        data=items, total_items=total,
        page=page, page_size=page_size,
        message="Sentiment logs retrieved.",
    )


# ── GET /sentiment/logs/{sentiment_id} ───────────────────────

@router.get(
    "/logs/{sentiment_id}",
    summary="Get a single sentiment log by SID-... identifier",
)
async def get_log(
    sentiment_id: str,
    current_user: dict                   = Depends(get_current_user),
    col:          AsyncIOMotorCollection = Depends(SentimentLogsCollection),
):
    doc = await get_sentiment_log(col, sentiment_id)
    if not doc:
        raise NotFoundError(
            f"Sentiment log '{sentiment_id}' not found.",
            error_code="SENTIMENT_LOG_NOT_FOUND",
        )
    return success_response(
        data=SentimentLogOut(**{**doc, "id": doc["_id"]}).model_dump(),
        message="Sentiment log retrieved.",
    )


# ── GET /sentiment/summary ────────────────────────────────────

@router.get(
    "/summary",
    summary="Aggregated sentiment counts",
)
async def get_summary(
    current_user: dict                   = Depends(get_current_user),
    col:          AsyncIOMotorCollection = Depends(SentimentLogsCollection),
):
    role    = current_user.get("role", "customer")
    user_id = current_user.get("_id") if role != "admin" else None
    data    = await sentiment_summary(col, user_id=user_id)
    return success_response(data=data, message="Sentiment summary retrieved.")


# ── GET /sentiment/labels ─────────────────────────────────────

@router.get(
    "/labels",
    summary="List all supported sentiment labels with metadata",
)
async def list_labels(
    current_user: dict = Depends(get_current_user),
):
    data = [
        {
            "sentiment":     k,
            "label":         v["label"],
            "description":   v["description"],
            "examples":      v["examples"],
            "polarity_score": v["polarity"],
            "emoji":         v["emoji"],
        }
        for k, v in SENTIMENT_META.items()
    ]
    return success_response(data=data, message=f"{len(data)} sentiment labels supported.")
