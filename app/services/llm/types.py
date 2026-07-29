from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class AIResponse:
    text: str
    tokens_used: int
    model_used: str
    provider: str
    is_fallback: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


class AIError(Exception):
    def __init__(self, message: str, error_code: str = "AI_ERROR", retryable: bool = False):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.retryable = retryable


class AIProvider:
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
        metadata: Optional[dict[str, Any]] = None,
    ) -> AIResponse:
        raise NotImplementedError()
