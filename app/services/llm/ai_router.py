from __future__ import annotations

import logging
from typing import Any

from app.config import settings
from app.services.llm.types import AIResponse, AIError

logger = logging.getLogger(__name__)


class AIRouter:
    PROVIDER_ORDER = ["gemini", "openai", "groq", "deepseek"]

    def __init__(self, provider: str | None = None):
        self.provider = (provider or settings.AI_PROVIDER or "").strip().lower()

    def _provider_candidates(self) -> list[str]:
        if self.provider in self.PROVIDER_ORDER:
            return [self.provider] + [p for p in self.PROVIDER_ORDER if p != self.provider]
        return self.PROVIDER_ORDER.copy()

    async def generate(
        self,
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
        last_error = None
        for provider_name in self._provider_candidates():
            logger.info("AI Router trying provider %s", provider_name, extra={"component": "ai_router", "provider": provider_name})
            try:
                response = await self._call_provider(
                    provider_name=provider_name,
                    system_prompt=system_prompt,
                    history=history,
                    user_message=user_message,
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    top_p=top_p,
                    top_k=top_k,
                    timeout=timeout,
                    metadata=metadata,
                )
                logger.info(
                    "AI Router selected provider %s | model=%s | tokens=%d | fallback=%s",
                    provider_name,
                    response.model_used,
                    response.tokens_used,
                    response.is_fallback,
                    extra={"component": "ai_router", "provider": provider_name},
                )
                return response
            except AIError as exc:
                last_error = exc
                logger.warning(
                    "AI provider %s failed, falling back to next provider: %s",
                    provider_name,
                    exc.message,
                    extra={"component": "ai_router", "provider": provider_name, "retryable": exc.retryable},
                )
                if not exc.retryable:
                    continue
            except Exception as exc:
                last_error = AIError(str(exc), error_code="AI_UNEXPECTED_ERROR", retryable=True)
                logger.exception(
                    "Unexpected exception from AI provider %s, falling back.",
                    provider_name,
                    extra={"component": "ai_router", "provider": provider_name},
                )
        if last_error:
            raise last_error
        raise AIError("No AI provider available.", error_code="AI_NO_PROVIDER", retryable=False)

    async def _call_provider(
        self,
        provider_name: str,
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
        if provider_name == "gemini":
            from app.services.gemini.adapter import GeminiAdapter
            return await GeminiAdapter.generate(
                system_prompt=system_prompt,
                history=history,
                user_message=user_message,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                top_k=top_k,
                timeout=timeout,
                metadata=metadata,
            )
        if provider_name == "openai":
            from app.services.openai.openai_service import OpenAIService
            return await OpenAIService.generate(
                system_prompt=system_prompt,
                history=history,
                user_message=user_message,
                model=settings.OPENAI_MODEL,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                top_k=top_k,
                timeout=timeout,
                metadata=metadata,
            )
        if provider_name == "groq":
            from app.services.groq.groq_service import GroqService
            return await GroqService.generate(
                system_prompt=system_prompt,
                history=history,
                user_message=user_message,
                model=settings.GROQ_MODEL,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                top_k=top_k,
                timeout=timeout,
                metadata=metadata,
            )
        if provider_name == "deepseek":
            from app.services.deepseek.deepseek_service import DeepSeekService
            return await DeepSeekService.generate(
                system_prompt=system_prompt,
                history=history,
                user_message=user_message,
                model=settings.DEEPSEEK_MODEL,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                top_k=top_k,
                timeout=timeout,
                metadata=metadata,
            )
        raise AIError(f"Unknown provider {provider_name}", error_code="AI_UNKNOWN_PROVIDER", retryable=False)
