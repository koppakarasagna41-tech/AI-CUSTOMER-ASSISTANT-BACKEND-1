"""
app/knowledge/vector_store/chroma_service.py
──────────────────────────────────────────────
ChromaDB persistence service.

Manages the `knowledge_base_vectors` collection in ChromaDB.
All operations are wrapped in a thread executor so they don't
block the async event loop (ChromaDB client is synchronous).

Public API:
  get_chroma_client()                    → ChromaDB client singleton
  get_or_create_collection()             → Collection handle
  upsert_chunks(chunks, vectors)         → store/update embeddings
  delete_by_document_id(document_id)     → remove all chunks of a doc
  get_collection_count()                 → int
  collection_exists()                    → bool
"""

import asyncio
import logging
import os
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

# ── Singleton state ───────────────────────────────────────────
_chroma_client     = None
_chroma_collection = None


def _get_client():
    """Return (and cache) the ChromaDB PersistentClient."""
    global _chroma_client
    if _chroma_client is None:
        try:
            import chromadb
            persist_dir = settings.CHROMA_PERSIST_DIR
            os.makedirs(persist_dir, exist_ok=True)
            _chroma_client = chromadb.PersistentClient(path=persist_dir)
            logger.info("ChromaDB client initialised | path=%s", persist_dir)
        except ImportError:
            raise RuntimeError(
                "chromadb is not installed. Run: pip install chromadb"
            )
    return _chroma_client


def _get_collection():
    """Return (and cache) the knowledge_base_vectors collection."""
    global _chroma_collection
    if _chroma_collection is None:
        client = _get_client()
        _chroma_collection = client.get_or_create_collection(
            name=settings.CHROMA_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            "ChromaDB collection ready: %s | count=%d",
            settings.CHROMA_COLLECTION_NAME,
            _chroma_collection.count(),
        )
    return _chroma_collection


# ── Async wrappers ────────────────────────────────────────────

async def upsert_chunks(
    chunk_ids:    list[str],
    embeddings:   list[list[float]],
    documents:    list[str],
    metadatas:    list[dict],
) -> None:
    """
    Upsert a batch of chunk embeddings into ChromaDB.

    Args:
        chunk_ids  : list of chunk_id strings (used as ChromaDB IDs)
        embeddings : list of float vectors (one per chunk)
        documents  : list of chunk text content
        metadatas  : list of metadata dicts
    """
    if not chunk_ids:
        return

    def _blocking() -> None:
        col = _get_collection()
        col.upsert(
            ids=chunk_ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _blocking)
    logger.debug("ChromaDB upsert: %d vectors", len(chunk_ids))


async def delete_by_document_id(document_id: str) -> int:
    """
    Delete all vectors belonging to a document.
    Returns the number of deleted items.
    """
    def _blocking() -> int:
        col     = _get_collection()
        results = col.get(where={"document_id": document_id}, include=[])
        ids     = results.get("ids", [])
        if ids:
            col.delete(ids=ids)
        return len(ids)

    loop = asyncio.get_event_loop()
    deleted = await loop.run_in_executor(None, _blocking)
    logger.info("ChromaDB: deleted %d vectors for document_id=%s", deleted, document_id)
    return deleted


async def get_collection_count() -> int:
    """Return total number of vectors stored in ChromaDB."""
    def _blocking() -> int:
        return _get_collection().count()

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _blocking)


async def collection_exists() -> bool:
    """Check if the ChromaDB collection exists and is reachable."""
    try:
        count = await get_collection_count()
        return True
    except Exception as exc:
        logger.warning("ChromaDB collection check failed: %s", exc)
        return False


def reset_client() -> None:
    """
    Reset the ChromaDB singleton — used in tests.
    """
    global _chroma_client, _chroma_collection
    _chroma_client     = None
    _chroma_collection = None
