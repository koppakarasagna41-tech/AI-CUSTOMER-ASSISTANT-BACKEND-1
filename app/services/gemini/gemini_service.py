"""
app/services/gemini/gemini_service.py
───────────────────────────────────────
Public service facade for all Gemini operations.

Routers import this module; they do NOT import the api_wrapper or
response_generator directly.  This single entry point keeps the
router layer thin and makes testing straightforward.

Exported:
  GeminiService  — class with static async methods
"""

import logging
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorCollection

from app.config    import settings
from .api_wrapper  import GeminiConfigError, generate_content_async
from .prompt_manager     import PromptManager
from .response_generator import GeminiResult, generate_ai_response

logger = logging.getLogger(__name__)


class GeminiService:
    """
    High-level facade for Gemini AI operations.

    All methods are static so they can be called without instantiation,
    matching the pattern used throughout this project (stateless services).
    """

    # ── Primary operation ─────────────────────────────────────

    @staticmethod
    async def chat(
        *,
        conversation_id:   str,
        user_message:      str,
        conversations_col: AsyncIOMotorCollection,
        messages_col:      AsyncIOMotorCollection,
        user_name:         Optional[str] = None,
    ) -> GeminiResult:
        """
        Process a user message in a conversation and return the AI response.

        This is the single method the chat router calls.
        It delegates to generate_ai_response() for the full pipeline.

        Args:
            conversation_id   : Existing conversation's human-readable ID
            user_message      : Raw text from the user
            conversations_col : Motor conversations collection
            messages_col      : Motor messages collection
            user_name         : Optional display name for greeting

        Returns:
            GeminiResult with AI reply + metadata
        """
        logger.info(
            "GeminiService.chat | conversation=%s | user=%s | msg_len=%d",
            conversation_id,
            user_name or "anonymous",
            len(user_message),
        )
        return await generate_ai_response(
            conversation_id=conversation_id,
            user_message_text=user_message,
            conversations_col=conversations_col,
            messages_col=messages_col,
            user_name=user_name,
        )

    # ── Utility operations ────────────────────────────────────

    @staticmethod
    async def generate_conversation_title(text: str) -> str:
        """
        Use Gemini to generate a concise title for a conversation.
        Falls back to a truncated version of the text if Gemini fails.

        Args:
            text : First user message or combined conversation snippet

        Returns:
            Short title string (max ~60 chars)
        """
        if not settings.GEMINI_API_KEY or settings.GEMINI_API_KEY == "your-gemini-api-key-here":
            return _truncate_title(text)

        prompt = PromptManager.summary_prompt(text)
        try:
            title, _ = await generate_content_async(
                model_name=settings.GEMINI_MODEL,
                system_prompt="You are a helpful assistant that writes concise titles.",
                history=[],
                user_message=prompt,
                max_tokens=30,
                temperature=0.3,
                top_p=0.9,
                top_k=20,
                timeout=10,
            )
            return title[:80] if title else _truncate_title(text)
        except Exception as exc:
            logger.exception("Title generation failed, using fallback.")
            return _truncate_title(text)

    @staticmethod
    def is_configured() -> bool:
        """Return True if GEMINI_API_KEY is set and non-placeholder."""
        key = settings.GEMINI_API_KEY
        return bool(key and key != "your-gemini-api-key-here")

    @staticmethod
    def get_model_info() -> dict:
        """Return current Gemini model configuration (safe to expose in /health)."""
        return {
            "model":       settings.GEMINI_MODEL,
            "max_tokens":  settings.GEMINI_MAX_TOKENS,
            "temperature": settings.GEMINI_TEMPERATURE,
            "configured":  GeminiService.is_configured(),
        }


# ── Internal helpers ──────────────────────────────────────────

def _truncate_title(text: str, max_len: int = 60) -> str:
    text = text.strip()
    if len(text) <= max_len:
        return text
    return text[:max_len].rsplit(" ", 1)[0] + "…"
