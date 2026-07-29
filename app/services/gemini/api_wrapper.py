"""
app/services/gemini/api_wrapper.py
────────────────────────────────────
Low-level async wrapper around the google-generativeai SDK.

Responsibilities:
  - Configure the Gemini client once at module import.
  - Expose a single async function: generate_content_async()
  - Translate SDK exceptions → application-level GeminiError.
  - Apply retry logic for transient failures (rate limits, timeouts).
  - Never contain business logic — callers decide what to do with errors.

Design:
  google-generativeai's async methods are used directly.
  We run the blocking SDK call in a thread executor for safety
  since the SDK's async support can be inconsistent across versions.
"""

import asyncio
import logging
import time
from typing import Any

import google.generativeai as genai
from google.api_core.exceptions import (
    DeadlineExceeded,
    GoogleAPICallError,
    ResourceExhausted,
    ServiceUnavailable,
)

from app.config import settings

logger = logging.getLogger(__name__)

# ── Configure SDK once at import time ────────────────────────
# The API key is validated at startup via validate_gemini_config()
_client_configured = False


def _ensure_configured() -> None:
    """Configure genai SDK if not already done."""
    global _client_configured
    if not _client_configured:
        if not settings.GEMINI_API_KEY or settings.GEMINI_API_KEY == "your-gemini-api-key-here":
            raise GeminiConfigError(
                "GEMINI_API_KEY is not set. "
                "Add it to your .env file: GEMINI_API_KEY=your-key"
            )
        genai.configure(api_key=settings.GEMINI_API_KEY)
        _client_configured = True


# ── Custom exceptions ─────────────────────────────────────────

class GeminiError(Exception):
    """Base exception for all Gemini API failures."""
    def __init__(self, message: str, error_code: str = "GEMINI_ERROR", retryable: bool = False):
        super().__init__(message)
        self.message    = message
        self.error_code = error_code
        self.retryable  = retryable


class GeminiConfigError(GeminiError):
    """Raised when the API key or model config is invalid."""
    def __init__(self, message: str):
        super().__init__(message, error_code="GEMINI_CONFIG_ERROR", retryable=False)


class GeminiRateLimitError(GeminiError):
    """Raised on 429 / quota exhaustion."""
    def __init__(self, message: str = "Gemini API rate limit reached. Try again shortly."):
        super().__init__(message, error_code="GEMINI_RATE_LIMIT", retryable=True)


class GeminiTimeoutError(GeminiError):
    """Raised when the Gemini request exceeds GEMINI_TIMEOUT seconds."""
    def __init__(self, message: str = "Gemini API request timed out."):
        super().__init__(message, error_code="GEMINI_TIMEOUT", retryable=True)


class GeminiServiceError(GeminiError):
    """Raised for 5xx / transient Google service errors."""
    def __init__(self, message: str = "Gemini service is temporarily unavailable."):
        super().__init__(message, error_code="GEMINI_SERVICE_ERROR", retryable=True)


class GeminiContentFilterError(GeminiError):
    """Raised when Gemini blocks content due to safety filters."""
    def __init__(self, message: str = "Response blocked by Gemini safety filters."):
        super().__init__(message, error_code="GEMINI_CONTENT_FILTERED", retryable=False)


# ── Core async wrapper ────────────────────────────────────────

async def generate_content_async(
    *,
    model_name:    str,
    system_prompt: str,
    history:       list[dict[str, Any]],
    user_message:  str,
    max_tokens:    int,
    temperature:   float,
    top_p:         float,
    top_k:         int,
    timeout:       int,
) -> tuple[str, int]:
    """
    Send a multi-turn request to Gemini and return (response_text, tokens_used).

    Args:
        model_name    : Gemini model identifier (e.g. "gemini-1.5-flash")
        system_prompt : Instructions injected as a system message
        history       : Previous turns as [{"role": "user"|"model", "parts": [...]}]
        user_message  : Current user message
        max_tokens    : Maximum output tokens
        temperature   : Sampling temperature (0.0–1.0)
        top_p         : Nucleus sampling probability
        top_k         : Top-K sampling
        timeout       : Request timeout in seconds

    Returns:
        (response_text: str, tokens_used: int)

    Raises:
        GeminiConfigError       — API key missing or invalid
        GeminiRateLimitError    — quota exhausted
        GeminiTimeoutError      — request exceeded timeout
        GeminiServiceError      — transient Google error
        GeminiContentFilterError — safety filter blocked response
        GeminiError             — any other Gemini failure
    """
    _ensure_configured()

    logger.info(
        "Gemini request started",
        extra={
            "component": "gemini",
            "event": "request_started",
            "model": model_name,
            "history_length": len(history),
            "message_length": len(user_message),
            "timeout": timeout,
        },
    )
    start_time = time.perf_counter()

    generation_config = genai.types.GenerationConfig(
        max_output_tokens=max_tokens,
        temperature=temperature,
        top_p=top_p,
        top_k=top_k,
    )

    def _blocking_call() -> tuple[str, int]:
        """Run the synchronous SDK call (wraps in executor below)."""
        model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=system_prompt,
            generation_config=generation_config,
        )

        # Start a chat session with existing history
        chat   = model.start_chat(history=history)
        result = chat.send_message(user_message)

        # Extract text safely
        if not result.candidates:
            raise GeminiContentFilterError()

        candidate = result.candidates[0]

        # Check finish reason for safety blocks
        finish_reason = getattr(candidate, "finish_reason", None)
        if finish_reason and str(finish_reason) in ("SAFETY", "3"):
            raise GeminiContentFilterError()

        text        = result.text or ""
        tokens_used = getattr(result.usage_metadata, "total_token_count", 0) or 0
        return text.strip(), tokens_used

    # Run blocking SDK call in a thread pool to keep the event loop free
    loop = asyncio.get_event_loop()
    try:
        response_text, tokens_used = await asyncio.wait_for(
            loop.run_in_executor(None, _blocking_call),
            timeout=float(timeout),
        )
        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            "Gemini request completed",
            extra={
                "component": "gemini",
                "event": "request_completed",
                "model": model_name,
                "response_length": len(response_text),
                "tokens_used": tokens_used,
                "duration_ms": round(duration_ms, 3),
            },
        )
        return response_text, tokens_used

    except asyncio.TimeoutError:
        logger.warning(
            "Gemini request timed out",
            extra={"component": "gemini", "event": "request_failed", "model": model_name, "timeout": timeout},
        )
        raise GeminiTimeoutError()

    except GeminiError:
        raise   # re-raise our own typed errors without wrapping

    except ResourceExhausted as exc:
        logger.warning(
            "Gemini rate limit reached",
            extra={"component": "gemini", "event": "rate_limit", "model": model_name, "error": str(exc)},
        )
        raise GeminiRateLimitError()

    except DeadlineExceeded as exc:
        logger.warning(
            "Gemini deadline exceeded",
            extra={"component": "gemini", "event": "timeout", "model": model_name, "error": str(exc)},
        )
        raise GeminiTimeoutError()

    except ServiceUnavailable as exc:
        logger.warning(
            "Gemini service unavailable",
            extra={"component": "gemini", "event": "service_unavailable", "model": model_name, "error": str(exc)},
        )
        raise GeminiServiceError()

    except GoogleAPICallError as exc:
        logger.error(
            "Gemini API call error",
            extra={"component": "gemini", "event": "request_failed", "model": model_name, "error": str(exc)},
        )
        raise GeminiError(
            message=f"Gemini API error: {str(exc)}",
            error_code="GEMINI_API_ERROR",
            retryable=False,
        )

    except Exception as exc:
        logger.exception(
            "Unexpected error calling Gemini",
            extra={"component": "gemini", "event": "request_failed", "model": model_name, "error": str(exc)},
        )
        raise GeminiError(
            message="Unexpected error communicating with Gemini.",
            error_code="GEMINI_UNEXPECTED_ERROR",
            retryable=False,
        )
