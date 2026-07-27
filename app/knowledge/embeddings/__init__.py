# app/knowledge/embeddings package
from .embedding_service import (
    embed_texts,
    embed_text,
    is_embedding_configured,
    EmbeddingError,
    EmbeddingConfigError,
)

__all__ = [
    "embed_texts", "embed_text",
    "is_embedding_configured",
    "EmbeddingError", "EmbeddingConfigError",
]
