"""
app/rag/embeddings/query_embedder.py
──────────────────────────────────────
Generates query embeddings for RAG similarity search.

Uses task_type='retrieval_query' (vs 'retrieval_document' used at
index time) to get asymmetric embeddings optimised for retrieval.
"""

import logging
from typing import Optional

from app.knowledge.embeddings.embedding_service import embed_text, EmbeddingError

logger = logging.getLogger(__name__)


async def embed_query(
    question:   str,
    model_name: Optional[str] = None,
) -> list[float]:
    """
    Generate a single embedding vector for a customer query.

    Args:
        question   : The customer's question text
        model_name : Override embedding model (uses settings default if None)

    Returns:
        Float vector (768 dims for text-embedding-004)

    Raises:
        EmbeddingError — if the Gemini API call fails
    """
    if not question.strip():
        raise ValueError("Query cannot be empty.")

    logger.debug("Embedding query: %d chars", len(question))

    vector = await embed_text(
        text=question.strip(),
        task_type="retrieval_query",
        model_name=model_name,
    )

    logger.debug("Query embedding generated: %d dims", len(vector))
    return vector
