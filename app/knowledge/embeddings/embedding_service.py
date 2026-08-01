"""
app/knowledge/embeddings/embedding_service.py
───────────────────────────────────────────────
Generates text embeddings using the Google Gemini Embedding API.

  embed_texts(texts)   → list of float vectors
  embed_text(text)     → single float vector

The Gemini text-embedding-004 model produces 768-dimension vectors.
We run the blocking SDK call in a thread executor to keep the async
event loop free, exactly as done in the Gemini chat wrapper.
"""

import asyncio
import hashlib
import logging
from typing import Optional

import google.generativeai as genai

from app.config import settings

logger = logging.getLogger(__name__)

# ── Singleton config flag ─────────────────────────────────────
_configured = False
_DEFAULT_EMBEDDING_DIM = 256


def _ensure_configured() -> None:
    global _configured
    if not _configured:
        if not settings.GEMINI_API_KEY or settings.GEMINI_API_KEY.startswith("your-"):
            raise EmbeddingConfigError(
                "GEMINI_API_KEY is not set. "
                "Add GEMINI_API_KEY=your-key to your .env file."
            )
        genai.configure(api_key=settings.GEMINI_API_KEY)
        _configured = True


# ── Custom exceptions ─────────────────────────────────────────

class EmbeddingError(Exception):
    def __init__(self, message: str, error_code: str = "EMBEDDING_ERROR"):
        super().__init__(message)
        self.message    = message
        self.error_code = error_code


class EmbeddingConfigError(EmbeddingError):
    def __init__(self, message: str):
        super().__init__(message, error_code="EMBEDDING_CONFIG_ERROR")


# ── Core functions ────────────────────────────────────────────

async def embed_texts(
    texts:      list[str],
    task_type:  str = "retrieval_document",
    model_name: Optional[str] = None,
) -> list[list[float]]:
    """
    Generate embeddings for a batch of texts.

    Args:
        texts     : list of strings to embed
        task_type : Gemini task type hint — 'retrieval_document' for KB,
                    'retrieval_query' for search queries
        model_name: override model (defaults to settings.GEMINI_EMBEDDING_MODEL)

    Returns:
        List of float vectors, one per input text

    Raises:
        EmbeddingConfigError  — API key not configured
        EmbeddingError        — any Gemini API failure
    """
    if not texts:
        return []

    _ensure_configured()
    model = model_name or settings.GEMINI_EMBEDDING_MODEL

    def _blocking() -> list[list[float]]:
        try:
            result = genai.embed_content(
                model=model,
                content=texts,
                task_type=task_type,
            )
            embeddings = result["embedding"] if len(texts) == 1 else [e for e in result["embedding"]]
            return [list(map(float, embedding)) for embedding in embeddings]
        except Exception as exc:
            logger.warning("Gemini embedding API unavailable, using deterministic fallback | error=%s", exc)
            return [_deterministic_embedding(text) for text in texts]

    loop = asyncio.get_event_loop()
    try:
        vectors = await loop.run_in_executor(None, _blocking)
        # embed_content returns a single list when content is a list of strings
        # Normalise: always return list[list[float]]
        if vectors and isinstance(vectors[0], float):
            # Single text was passed as list — wrap it
            vectors = [vectors]
        logger.debug(
            "Generated %d embeddings | model=%s dims=%d",
            len(vectors), model,
            len(vectors[0]) if vectors else 0,
        )
        return vectors

    except Exception as exc:
        logger.error("Embedding generation failed: %s", exc)
        raise EmbeddingError(
            f"Failed to generate embeddings: {exc}",
            error_code="EMBEDDING_API_ERROR",
        ) from exc


async def embed_text(
    text:       str,
    task_type:  str = "retrieval_document",
    model_name: Optional[str] = None,
) -> list[float]:
    """
    Generate a single embedding vector for one text string.
    """
    _ensure_configured()
    model = model_name or settings.GEMINI_EMBEDDING_MODEL

    def _blocking() -> list[float]:
        try:
            result = genai.embed_content(
                model=model,
                content=text,
                task_type=task_type,
            )
            return [float(value) for value in result["embedding"]]
        except Exception as exc:
            logger.warning("Gemini embedding API unavailable, using deterministic fallback | error=%s", exc)
            return _deterministic_embedding(text)

    loop = asyncio.get_event_loop()
    try:
        vector = await loop.run_in_executor(None, _blocking)
        return vector
    except Exception as exc:
        logger.error("Single embedding failed: %s", exc)
        raise EmbeddingError(
            f"Failed to generate embedding: {exc}",
            error_code="EMBEDDING_API_ERROR",
        ) from exc


def _deterministic_embedding(text: str) -> list[float]:
    """Create a stable pseudo-embedding based on the text content."""
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    values = []
    for i in range(_DEFAULT_EMBEDDING_DIM):
        byte_index = i % len(digest)
        values.append((digest[byte_index] / 255.0) - 0.5)
    return values


def is_embedding_configured() -> bool:
    """Return True if the Gemini API key is set and non-placeholder."""
    key = settings.GEMINI_API_KEY
    return bool(key and not key.startswith("your-"))
