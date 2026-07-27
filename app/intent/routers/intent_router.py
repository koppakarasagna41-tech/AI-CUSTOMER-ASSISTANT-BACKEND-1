"""
app/intent/routers/intent_router.py
─────────────────────────────────────
Intent Detection API endpoints.

POST /intent/detect
    Classify a single message → returns intent + confidence score.
    Saves result to MongoDB intent_logs.

POST /intent/detect/batch
    Classify up to 20 messages at once.

GET  /intent/logs
    Paginated list of stored intent logs with optional filters.

GET  /intent/logs/{intent_id}
    Fetch a single intent log by its ID.

GET  /intent/logs/conversation/{conversation_id}
    All intents detected within a specific conversation.

GET  /intent/summary
    Aggregated intent counts — useful for analytics dashboards.

GET  /intent/intents
    List all supported intents with metadata.

All endpoints require a valid Bearer token.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from motor.motor_asyncio import AsyncIOMotorCollection

from app.core.auth_deps  import get_current_user
from app.core.exceptions import NotFoundError
from app.core.responses  import success_response, paginated_response
from app.database        import IntentLogsCollection

from app.intent.constants import Intent, INTENT_META
from app.intent.schemas   import (
    IntentRequest, IntentResult, IntentLogOut,
    IntentBatchRequest, IntentBatchResult,
)
from app.intent.schemas.intent  import IntentScore
from app.intent.services        import (
    classify_intent, save_intent_log,
    get_intent_log, list_intent_logs,
    get_conversation_intents, intent_summary,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/intent", tags=["Intent Detection"])


# ── Helper: result → IntentResult schema ─────────────────────

def _to_schema(result, intent_id: Optional[str] = None) -> IntentResult:
    scores = [
        IntentScore(
            intent=k,
            label=INTENT_META.get(k, {}).get("label", k.replace("_", " ").title()),
            score=v,
        )
        for k, v in sorted(result.all_scores.items(), key=lambda x: x[1], reverse=True)
    ]
    return IntentResult(
        message=result.message,
        intent=result.intent,
        label=result.label,
        confidence=result.confidence,
        is_confident=result.is_confident,
        all_scores=scores,
        prompt_category=result.prompt_category,
        model_used=result.model_used,
        tokens_used=result.tokens_used,
        latency_ms=result.latency_ms,
        intent_id=intent_id,
        conversation_id=None,
    )


# ── POST /intent/detect ───────────────────────────────────────

@router.post(
    "/detect",
    summary="Detect intent of a customer message",
)
async def detect_intent(
    payload:      IntentRequest,
    current_user: dict                   = Depends(get_current_user),
    col:          AsyncIOMotorCollection = Depends(IntentLogsCollection),
):
    """
    Classify the intent of a customer message using Gemini.

    Returns:
    - `intent`       — winning intent label
    - `confidence`   — score 0.0–1.0
    - `is_confident` — True if score ≥ configured threshold
    - `all_scores`   — probability for every intent class
    - `prompt_category` — maps to a prompt template for response generation
    """
    result = await classify_intent(message=payload.message)

    # Persist to MongoDB
    intent_id = await save_intent_log(
        col=col,
        result=result,
        user_id=current_user.get("_id"),
        conversation_id=payload.conversation_id,
    )

    schema = _to_schema(result, intent_id=intent_id)
    schema.conversation_id = payload.conversation_id

    logger.info(
        "Intent detected | id=%s intent=%s confidence=%.3f user=%s",
        intent_id, result.intent, result.confidence,
        current_user.get("_id"),
    )

    return success_response(
        data=schema.model_dump(),
        message=f"Intent detected: {result.label}",
    )


# ── POST /intent/detect/batch ─────────────────────────────────

@router.post(
    "/detect/batch",
    summary="Classify multiple messages at once (max 20)",
)
async def detect_intent_batch(
    payload:      IntentBatchRequest,
    current_user: dict                   = Depends(get_current_user),
    col:          AsyncIOMotorCollection = Depends(IntentLogsCollection),
):
    """
    Classify up to 20 messages in a single request.
    Each message is classified independently.
    Results are saved individually to MongoDB.
    """
    import asyncio

    async def _classify_one(message: str) -> IntentResult:
        result    = await classify_intent(message=message)
        intent_id = await save_intent_log(
            col=col,
            result=result,
            user_id=current_user.get("_id"),
            conversation_id=payload.conversation_id,
        )
        s = _to_schema(result, intent_id=intent_id)
        s.conversation_id = payload.conversation_id
        return s

    # Run all classifications concurrently
    results = await asyncio.gather(
        *[_classify_one(m) for m in payload.messages]
    )

    batch = IntentBatchResult(results=list(results), total=len(results))

    return success_response(
        data=batch.model_dump(),
        message=f"Classified {len(results)} messages.",
    )


# ── GET /intent/logs ──────────────────────────────────────────

@router.get(
    "/logs",
    summary="List stored intent logs",
)
async def list_logs(
    page:            int           = Query(1,    ge=1),
    page_size:       int           = Query(20,   ge=1, le=100),
    intent:          Optional[str] = Query(None, description="Filter by intent label"),
    is_fallback:     Optional[bool]= Query(None, description="Filter by fallback status"),
    conversation_id: Optional[str] = Query(None),
    current_user:    dict                   = Depends(get_current_user),
    col:             AsyncIOMotorCollection = Depends(IntentLogsCollection),
):
    """Return paginated intent detection logs. Admins see all; others see their own."""
    role    = current_user.get("role", "customer")
    user_id = current_user.get("_id") if role != "admin" else None

    skip        = (page - 1) * page_size
    docs, total = await list_intent_logs(
        col=col,
        skip=skip,
        limit=page_size,
        intent=intent,
        user_id=user_id,
        conversation_id=conversation_id,
        is_fallback=is_fallback,
    )

    items = [
        IntentLogOut(**{**d, "id": d["_id"]}).model_dump()
        for d in docs
    ]

    return paginated_response(
        data=items, total_items=total,
        page=page, page_size=page_size,
        message="Intent logs retrieved.",
    )


# ── GET /intent/logs/{intent_id} ──────────────────────────────

@router.get(
    "/logs/{intent_id}",
    summary="Get a single intent log by ID",
)
async def get_log(
    intent_id:    str,
    current_user: dict                   = Depends(get_current_user),
    col:          AsyncIOMotorCollection = Depends(IntentLogsCollection),
):
    doc = await get_intent_log(col, intent_id)
    if not doc:
        raise NotFoundError(
            f"Intent log '{intent_id}' not found.",
            error_code="INTENT_LOG_NOT_FOUND",
        )
    return success_response(
        data=IntentLogOut(**{**doc, "id": doc["_id"]}).model_dump(),
        message="Intent log retrieved.",
    )


# ── GET /intent/logs/conversation/{conversation_id} ───────────

@router.get(
    "/logs/conversation/{conversation_id}",
    summary="Get all intents detected in a conversation",
)
async def get_conversation_intent_logs(
    conversation_id: str,
    current_user:    dict                   = Depends(get_current_user),
    col:             AsyncIOMotorCollection = Depends(IntentLogsCollection),
):
    docs  = await get_conversation_intents(col, conversation_id)
    items = [
        IntentLogOut(**{**d, "id": d["_id"]}).model_dump()
        for d in docs
    ]
    return success_response(
        data=items,
        message=f"{len(items)} intent(s) found for conversation.",
    )


# ── GET /intent/summary ───────────────────────────────────────

@router.get(
    "/summary",
    summary="Aggregated intent counts",
)
async def get_summary(
    current_user: dict                   = Depends(get_current_user),
    col:          AsyncIOMotorCollection = Depends(IntentLogsCollection),
):
    """
    Returns how many times each intent has been detected.
    Admins see all data; other users see only their own.
    """
    role    = current_user.get("role", "customer")
    user_id = current_user.get("_id") if role != "admin" else None

    summary = await intent_summary(col, user_id=user_id)

    return success_response(
        data=summary,
        message="Intent summary retrieved.",
    )


# ── GET /intent/intents ───────────────────────────────────────

@router.get(
    "/intents",
    summary="List all supported intent types with metadata",
)
async def list_supported_intents(
    current_user: dict = Depends(get_current_user),
):
    """Returns the complete list of supported intents with descriptions and examples."""
    data = [
        {
            "intent":           k,
            "label":            v["label"],
            "description":      v["description"],
            "examples":         v["examples"],
            "prompt_category":  v["prompt_category"],
        }
        for k, v in INTENT_META.items()
    ]
    return success_response(
        data=data,
        message=f"{len(data)} intents supported.",
    )
