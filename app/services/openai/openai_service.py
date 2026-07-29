from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.config import settings
from app.services.llm.types import AIProvider, AIResponse
from app.services.openai.exceptions import OpenAIError

logger = logging.getLogger(__name__)

try:
    import openai
except ImportError:  # pragma: no cover
    openai = None


class OpenAIService(AIProvider):
    PROVIDER_NAME = "openai"

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
        if openai is None:
            raise OpenAIError("OpenAI SDK is unavailable.", error_code="OPENAI_SDK_MISSING", retryable=False)

        if not settings.OPENAI_API_KEY:
            raise OpenAIError("OpenAI API key is not configured.", error_code="OPENAI_CONFIG_ERROR", retryable=False)

        openai.api_key = settings.OPENAI_API_KEY
        model_name = model or settings.OPENAI_MODEL

        messages = [{"role": "system", "content": system_prompt}]
        for item in history:
            role = item.get("role", "user")
            content = item.get("content", "")
            if role not in ("system", "user", "assistant"):
                role = "user"
            messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": user_message})

        def _sync_request() -> tuple[str, int]:
            response = openai.ChatCompletion.create(
                model=model_name,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                n=1,
            )
            text = response.choices[0].message.content.strip()
            usage = response.usage.total_tokens if hasattr(response, "usage") else 0
            return text, usage

        try:
            text, tokens = await asyncio.wait_for(
                asyncio.to_thread(_sync_request),
                timeout=float(timeout),
            )
            return AIResponse(
                text=text,
                tokens_used=tokens,
                model_used=model_name,
                provider=OpenAIService.PROVIDER_NAME,
                is_fallback=False,
                metadata={"provider": OpenAIService.PROVIDER_NAME, **(metadata or {})},
            )
        except asyncio.TimeoutError:
            raise OpenAIError("OpenAI request timed out.", error_code="OPENAI_TIMEOUT", retryable=True)
        except Exception as exc:
            logger.exception("OpenAI request failed")
            raise OpenAIError(str(exc), error_code="OPENAI_ERROR", retryable=True)
