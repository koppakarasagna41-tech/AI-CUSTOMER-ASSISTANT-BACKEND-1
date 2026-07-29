from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.config import settings
from app.services.llm.types import AIProvider, AIResponse
from app.services.deepseek.exceptions import DeepSeekError

logger = logging.getLogger(__name__)

try:
    import deepseek
except ImportError:  # pragma: no cover
    deepseek = None


class DeepSeekService(AIProvider):
    PROVIDER_NAME = "deepseek"

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
        if deepseek is None:
            raise DeepSeekError("DeepSeek SDK is unavailable.", error_code="DEEPSEEK_SDK_MISSING", retryable=False)

        if not settings.DEEPSEEK_API_KEY:
            raise DeepSeekError("DeepSeek API key is not configured.", error_code="DEEPSEEK_CONFIG_ERROR", retryable=False)

        model_name = model or settings.DEEPSEEK_MODEL

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
            client = deepseek.Client(api_key=settings.DEEPSEEK_API_KEY)
            response = client.generate(
                model=model_name,
                prompt=prompt_text,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
            )
            text = getattr(response, "text", None)
            if text is None:
                text = str(response)
            text = text.strip()
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
                provider=DeepSeekService.PROVIDER_NAME,
                is_fallback=False,
                metadata={"provider": DeepSeekService.PROVIDER_NAME, **(metadata or {})},
            )
        except asyncio.TimeoutError:
            raise DeepSeekError("DeepSeek request timed out.", error_code="DEEPSEEK_TIMEOUT", retryable=True)
        except Exception as exc:
            logger.exception("DeepSeek request failed")
            raise DeepSeekError(str(exc), error_code="DEEPSEEK_ERROR", retryable=True)
