"""
app/rag/llm/gemini_rag.py
──────────────────────────
Calls the Gemini API for RAG-grounded answer generation.

Uses the existing api_wrapper but with:
  - No conversation history (single-turn RAG)
  - Lower temperature for factual, grounded responses
  - RAG-specific system prompt
"""

import logging
from dataclasses import dataclass

from app.config import settings
from app.services.gemini.api_wrapper import (
    generate_content_async,
    GeminiError,
    GeminiContentFilterError,
)
from app.rag.prompt_builder import build_rag_system_prompt, build_rag_user_message
from app.rag.retrieval.similarity_search import RetrievedChunk

logger = logging.getLogger(__name__)


@dataclass
class LLMResult:
    """Result returned from generate_rag_answer()."""
    answer:      str
    tokens_used: int
    model_used:  str
    is_fallback: bool = False


_FALLBACK_ANSWER = (
    "I'm experiencing a technical issue and couldn't process your question right now. "
    "Please try again in a moment or contact our support team directly."
)


async def generate_rag_answer(
    question: str,
    chunks:   list[RetrievedChunk],
) -> LLMResult:
    """
    Generate a grounded answer from Gemini using retrieved context.

    Args:
        question : Customer question
        chunks   : Ranked retrieved chunks from ChromaDB

    Returns:
        LLMResult with the answer text and metadata
    """
    system_prompt = build_rag_system_prompt()
    user_message  = build_rag_user_message(question, chunks)
    model         = settings.GEMINI_MODEL

    try:
        answer, tokens = await generate_content_async(
            model_name=model,
            system_prompt=system_prompt,
            history=[],                   # no history — single-turn RAG
            user_message=user_message,
            max_tokens=settings.GEMINI_MAX_TOKENS,
            temperature=0.2,              # lower temp for factual answers
            top_p=0.9,
            top_k=30,
            timeout=settings.GEMINI_TIMEOUT,
        )
        logger.info(
            "RAG answer generated | tokens=%d chars=%d",
            tokens, len(answer),
        )
        return LLMResult(
            answer=answer,
            tokens_used=tokens,
            model_used=model,
            is_fallback=False,
        )

    except GeminiContentFilterError:
        logger.warning("Gemini content filter triggered for RAG query")
        return LLMResult(
            answer=(
                "I'm sorry, I couldn't process that question due to content policy. "
                "Please rephrase and try again."
            ),
            tokens_used=0,
            model_used=model,
            is_fallback=True,
        )

    except GeminiError as exc:
        logger.error("Gemini error in RAG: %s", exc.message)
        return LLMResult(
            answer=_FALLBACK_ANSWER,
            tokens_used=0,
            model_used=model,
            is_fallback=True,
        )
