"""
app/rag/retrieval/similarity_search.py
────────────────────────────────────────
Performs cosine similarity search against ChromaDB.

Returns a list of RetrievedChunk dataclasses, each carrying
the text content, metadata, and the similarity score (0-1).

ChromaDB's 'cosine' distance is in [0,2] where 0 = identical.
We convert to similarity: similarity = 1 - (distance / 2)
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    """A single chunk returned from the similarity search."""
    chunk_id:    str
    document_id: str
    content:     str
    filename:    str
    category:    str
    page_number: int
    similarity:  float    # 0.0 (irrelevant) → 1.0 (identical)
    metadata:    dict


async def similarity_search(
    query_vector: list[float],
    top_k:        int = 5,
    category:     Optional[str] = None,
) -> list[RetrievedChunk]:
    """
    Query ChromaDB with a pre-computed embedding vector.

    Args:
        query_vector : float list from embed_query()
        top_k        : number of results to return
        category     : optional filter to restrict search to one category

    Returns:
        List of RetrievedChunk sorted by similarity (highest first).
        Empty list if ChromaDB has no vectors or returns no results.
    """
    where_filter: Optional[dict] = None
    if category:
        where_filter = {"category": category}

    def _blocking() -> list[RetrievedChunk]:
        # Import here to allow tests to mock chroma before it initialises
        from app.knowledge.vector_store.chroma_service import _get_collection

        try:
            col = _get_collection()
        except Exception as exc:
            logger.warning("ChromaDB unavailable: %s", exc)
            return []

        count = col.count()
        if count == 0:
            logger.info("ChromaDB collection is empty — no results.")
            return []

        # Clamp top_k to available docs
        effective_k = min(top_k, count)

        kwargs = dict(
            query_embeddings=[query_vector],
            n_results=effective_k,
            include=["documents", "metadatas", "distances"],
        )
        if where_filter:
            kwargs["where"] = where_filter

        results = col.query(**kwargs)

        chunks: list[RetrievedChunk] = []
        ids        = results.get("ids",        [[]])[0]
        documents  = results.get("documents",  [[]])[0]
        metadatas  = results.get("metadatas",  [[]])[0]
        distances  = results.get("distances",  [[]])[0]

        logger.info(
            "Retrieval results | query_vector_dims=%d top_k=%d count=%d",
            len(query_vector), top_k, len(ids),
        )

        for cid, doc, meta, dist in zip(ids, documents, metadatas, distances):
            # Convert cosine distance → similarity (ChromaDB cosine dist ∈ [0,2])
            similarity = max(0.0, 1.0 - (float(dist) / 2.0))
            logger.info(
                "Retrieved chunk | chunk_id=%s document_id=%s similarity=%.4f page=%s filename=%s",
                cid, meta.get("document_id", ""), similarity, meta.get("page_number", ""), meta.get("filename", ""),
            )
            chunks.append(RetrievedChunk(
                chunk_id=cid,
                document_id=meta.get("document_id", ""),
                content=doc or "",
                filename=meta.get("filename", ""),
                category=meta.get("category", ""),
                page_number=int(meta.get("page_number", 0)),
                similarity=round(similarity, 4),
                metadata=meta,
            ))

        # Sort highest similarity first (should already be sorted by ChromaDB)
        chunks.sort(key=lambda c: c.similarity, reverse=True)
        return chunks

    loop = asyncio.get_event_loop()
    chunks = await loop.run_in_executor(None, _blocking)

    logger.info(
        "Similarity search | top_k=%d found=%d best_score=%.3f",
        top_k,
        len(chunks),
        chunks[0].similarity if chunks else 0.0,
    )
    return chunks
