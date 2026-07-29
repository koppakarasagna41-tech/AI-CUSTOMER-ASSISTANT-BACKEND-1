from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.config import settings
from app.services.llm.types import AIProvider, AIResponse
from app.services.groq.exceptions import GroqError

logger = logging.getLogger(__name__)

try:
    import groq
except ImportError:  # pragma: no cover
    groq = None


class GroqService(AIProvider):
    PROVIDER_NAME = "groq"

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
        if groq is None:
            raise GroqError("Groq SDK is unavailable.", error_code="GROQ_SDK_MISSING", retryable=False)

        if not settings.GROQ_API_KEY:
            raise GroqError("Groq API key is not configured.", error_code="GROQ_CONFIG_ERROR", retryable=False)

        model_name = model or settings.GROQ_MODEL

        prompt_text = system_prompt
        if history:
            prompt_lines = [prompt_text, ""]
            for item in history:
                role = item.get("role", "user")
                if role == "assistant":
                    speaker = "Assistant"
                elif role == "system":
                    speaker = "System"
                else:
                    speaker = "User"
                prompt_lines.append(f"{speaker}: {item.get('content', '').strip()}")
            prompt_text = "\n".join(prompt_lines)
        prompt_text = f"{prompt_text}\n\nUser: {user_message.strip()}\nAssistant:"

        def _sync_request() -> tuple[str, int]:
            client = groq.Client(api_key=settings.GROQ_API_KEY)
            response = client.generate(
                model=model_name,
                prompt=prompt_text,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
            )
            text = response.text.strip() if hasattr(response, "text") else str(response).strip()
            tokens = getattr(response, "usage", {}).get("total_tokens", 0)
            return text, tokens

        try:
            text, tokens = await asyncio.wait_for(
                asyncio.to_thread(_sync_request),
                timeout=float(timeout),
            )
            return AIResponse(
                text=text,
                tokens_used=tokens,
                model_used=model_name,
                provider=GroqService.PROVIDER_NAME,
                is_fallback=False,
                metadata={"provider": GroqService.PROVIDER_NAME, **(metadata or {})},
            )
        except asyncio.TimeoutError:
            raise GroqError("Groq request timed out.", error_code="GROQ_TIMEOUT", retryable=True)
        except Exception as exc:
            logger.exception("Groq request failed")
            raise GroqError(str(exc), error_code="GROQ_ERROR", retryable=True)
