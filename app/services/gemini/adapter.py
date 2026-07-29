from __future__ import annotations

import logging
from typing import Any

from app.config import settings
from app.services.gemini.api_wrapper import generate_content_async, GeminiError, GeminiConfigError
from app.services.gemini.prompt_manager import PromptManager
from app.services.llm.types import AIProvider, AIResponse

logger = logging.getLogger(__name__)


class GeminiAdapter(AIProvider):
    PROVIDER_NAME = "gemini"

    @staticmethod
    async def generate(
        *,
        system_prompt: str,
        history: list[dict[str, str]],
        user_message: str,
        model: str,
        max_tokens: int,
        temperature: float,
        top_p: float,
        top_k: int,
        timeout: int,
        metadata: dict[str, Any] | None = None,
    ) -> AIResponse:
        if not settings.GEMINI_API_KEY or settings.GEMINI_API_KEY.startswith("your-"):
            raise GeminiConfigError("Gemini API key is not configured.")

        model_name = model or settings.GEMINI_MODEL

        gemini_history = [
            PromptManager.format_history_message(item.get("role", "user"), item.get("content", ""))
            for item in history
        ]

        try:
            text, tokens = await generate_content_async(
                model_name=model_name,
                system_prompt=system_prompt,
                history=gemini_history,
                user_message=user_message,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                top_k=top_k,
                timeout=timeout,
            )
            return AIResponse(
                text=text,
                tokens_used=tokens,
                model_used=model_name,
                provider=GeminiAdapter.PROVIDER_NAME,
                is_fallback=False,
                metadata={"provider": GeminiAdapter.PROVIDER_NAME, **(metadata or {})},
            )
        except GeminiError as exc:
            logger.exception("Gemini adapter failed")
            raise
        except Exception as exc:
            logger.exception("Unexpected Gemini adapter error")
            raise GeminiError(str(exc), error_code="GEMINI_ADAPTER_ERROR", retryable=True)
