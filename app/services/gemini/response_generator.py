"""
app/services/gemini/response_generator.py
───────────────────────────────────────────
Orchestrates a full Gemini chat exchange.

Responsibilities:
  1. Load the last N messages of conversation history from MongoDB.
  2. Format history into Gemini's expected multi-turn format.
  3. Call the API wrapper with system prompt + history + new message.
  4. Persist both the user message and the AI reply to MongoDB.
  5. Update conversation metadata (message_count, last_message_at, title).
  6. Return a structured GeminiResult.

This layer is the single source of truth for how a Gemini turn works.
Routers call generate_ai_response() and get back a GeminiResult.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorCollection

from app.config          import settings
from app.database.crud   import (
    create_document,
    get_document,
    get_documents,
    update_document,
)
from app.utils.helpers   import utc_now
from .api_wrapper        import (
    GeminiError,
    GeminiContentFilterError,
    generate_content_async,
)
from .prompt_manager     import PromptManager

logger = logging.getLogger(__name__)


# ── Result dataclass ──────────────────────────────────────────

@dataclass
class GeminiResult:
    """Returned from generate_ai_response() to the router."""
    user_message_id: str          # MongoDB _id of the saved user message
    ai_message_id:   str          # MongoDB _id of the saved AI message
    ai_content:      str          # AI reply text
    tokens_used:     int          # total tokens consumed
    model_used:      str          # model identifier
    conversation_id: str          # conversation_id string (not ObjectId)
    is_fallback:     bool = False  # True if we returned an error fallback message


# ── Main entry point ──────────────────────────────────────────

async def generate_ai_response(
    *,
    conversation_id:   str,               # e.g. "CONV-20260726-ABCD1234"
    user_message_text: str,
    conversations_col: AsyncIOMotorCollection,
    messages_col:      AsyncIOMotorCollection,
    user_name:         Optional[str] = None,
) -> GeminiResult:
    """
    Full Gemini turn — persist user message, call Gemini, persist AI reply.

    Args:
        conversation_id   : human-readable conversation identifier
        user_message_text : raw text sent by the user
        conversations_col : Motor collection for conversations
        messages_col      : Motor collection for messages
        user_name         : displayed name of the user (for greeting prompts)

    Returns:
        GeminiResult

    Never raises — on Gemini failure it persists a fallback message and
    returns is_fallback=True so the router can act accordingly.
    """
    now = utc_now()

    # ── 1. Verify conversation exists ────────────────────────
    conversation = await get_document(
        conversations_col,
        {"conversation_id": conversation_id},
    )
    if conversation is None:
        raise ValueError(f"Conversation '{conversation_id}' not found.")

    # ── 2. Save user message ──────────────────────────────────
    user_doc = {
        "conversation_id": conversation_id,
        "role":            "user",
        "content":         user_message_text.strip(),
        "status":          "sent",
        "tokens_used":     None,
        "model_used":      None,
        "metadata":        {},
        "created_at":      now,
        "updated_at":      now,
    }
    user_message_id = await create_document(messages_col, user_doc)

    # ── 3. Load conversation history ──────────────────────────
    history_docs = await get_documents(
        messages_col,
        filter_query={"conversation_id": conversation_id},
        # Fetch one extra for the message we just saved, then trim
        limit=settings.GEMINI_HISTORY_LIMIT + 1,
        sort=[("created_at", -1)],   # newest first
    )
    # Reverse to chronological order, exclude the message we just saved
    history_docs = list(reversed(history_docs))
    history_docs = [d for d in history_docs if d["_id"] != user_message_id]
    history_docs = history_docs[-(settings.GEMINI_HISTORY_LIMIT):]

    # Format for Gemini's multi-turn API
    is_first_message = len(history_docs) == 0
    formatted_history = [
        PromptManager.format_history_message(d["role"], d["content"])
        for d in history_docs
    ]

    # ── 4. Build system prompt ────────────────────────────────
    system = PromptManager.system_prompt()
    if is_first_message:
        system += "\n\n" + PromptManager.first_message_prompt(user_name)

    # ── 5. Call Gemini API ────────────────────────────────────
    ai_text    = ""
    tokens     = 0
    is_fallback = False
    model_used = settings.GEMINI_MODEL

    try:
        ai_text, tokens = await generate_content_async(
            model_name=settings.GEMINI_MODEL,
            system_prompt=system,
            history=formatted_history,
            user_message=user_message_text.strip(),
            max_tokens=settings.GEMINI_MAX_TOKENS,
            temperature=settings.GEMINI_TEMPERATURE,
            top_p=settings.GEMINI_TOP_P,
            top_k=settings.GEMINI_TOP_K,
            timeout=settings.GEMINI_TIMEOUT,
        )
        logger.info(
            "Gemini response generated | conversation=%s tokens=%d",
            conversation_id, tokens,
        )

    except GeminiContentFilterError as exc:
        logger.warning(
            "Gemini content filter triggered | conversation=%s | %s",
            conversation_id, exc.message,
        )
        ai_text     = (
            "I'm sorry, I couldn't process that message due to content policy. "
            "Please rephrase your question and I'll be happy to help."
        )
        is_fallback = True

    except GeminiError as exc:
        logger.error(
            "Gemini error | conversation=%s | code=%s | retryable=%s | %s",
            conversation_id, exc.error_code, exc.retryable, exc.message,
        )
        ai_text     = PromptManager.error_fallback_message()
        is_fallback = True

    # ── 6. Save AI reply ──────────────────────────────────────
    ai_doc = {
        "conversation_id": conversation_id,
        "role":            "assistant",
        "content":         ai_text,
        "status":          "delivered",
        "tokens_used":     tokens if not is_fallback else None,
        "model_used":      model_used if not is_fallback else None,
        "metadata":        {"is_fallback": is_fallback},
        "created_at":      utc_now(),
        "updated_at":      utc_now(),
    }
    ai_message_id = await create_document(messages_col, ai_doc)

    # ── 7. Update conversation metadata ───────────────────────
    new_count = conversation.get("message_count", 0) + 2   # user + AI

    conv_update: dict = {
        "message_count":   new_count,
        "last_message_at": utc_now().isoformat(),
        "updated_at":      utc_now(),
    }

    # Auto-set title from first exchange if not already set
    if not conversation.get("title") and not is_fallback:
        conv_update["title"] = _auto_title(user_message_text)

    await update_document(
        conversations_col,
        {"conversation_id": conversation_id},
        {"$set": conv_update},
    )

    return GeminiResult(
        user_message_id=user_message_id,
        ai_message_id=ai_message_id,
        ai_content=ai_text,
        tokens_used=tokens,
        model_used=model_used,
        conversation_id=conversation_id,
        is_fallback=is_fallback,
    )


# ── Helpers ───────────────────────────────────────────────────

def _auto_title(first_message: str, max_len: int = 60) -> str:
    """
    Generate a simple title from the first user message.
    Truncates at the last word boundary before max_len chars.
    """
    text = first_message.strip()
    if len(text) <= max_len:
        return text
    truncated = text[:max_len].rsplit(" ", 1)[0]
    return truncated + "…"
