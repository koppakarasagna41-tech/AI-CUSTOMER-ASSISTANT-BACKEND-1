"""
app/knowledge/services/mongo_service.py
─────────────────────────────────────────
MongoDB persistence layer for the Knowledge Base.

Handles CRUD for:
  - knowledge_documents  (document metadata)
  - knowledge_chunks     (chunk metadata, without vectors)

All functions accept Motor collections so they are easily testable.
"""

import logging
from datetime import datetime
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorCollection
from pymongo import DESCENDING

from app.database.crud import (
    create_document,
    get_document,
    get_document_by_id,
    get_documents,
    count_documents,
    update_document,
    update_document_by_id,
    delete_document,
    delete_document_by_id,
    document_exists,
)
from app.knowledge.chunking.chunking_service import TextChunk
from app.knowledge.models.document import DocumentStatus
from app.utils.helpers import utc_now

logger = logging.getLogger(__name__)


# ── Document operations ───────────────────────────────────────

async def create_knowledge_document(
    col:      AsyncIOMotorCollection,
    doc_data: dict,
) -> str:
    """Insert a new document record. Returns inserted _id string."""
    return await create_document(col, doc_data)


async def get_document_by_doc_id(
    col:         AsyncIOMotorCollection,
    document_id: str,
) -> Optional[dict]:
    """Fetch by human-readable document_id (e.g. KBD-20260726-ABCD)."""
    return await get_document(col, {"document_id": document_id})


async def get_document_record(
    col:    AsyncIOMotorCollection,
    obj_id: str,
) -> Optional[dict]:
    """Fetch by MongoDB _id string."""
    return await get_document_by_id(col, obj_id)


async def list_documents(
    col:        AsyncIOMotorCollection,
    skip:       int = 0,
    limit:      int = 20,
    category:   Optional[str] = None,
    status:     Optional[str] = None,
    doc_type:   Optional[str] = None,
    search:     Optional[str] = None,
) -> tuple[list[dict], int]:
    """
    Return (documents, total_count) with optional filters.
    """
    query: dict = {}
    if category:
        query["category"] = category
    if status:
        query["status"] = status
    if doc_type:
        query["doc_type"] = doc_type
    if search:
        query["$or"] = [
            {"original_name": {"$regex": search, "$options": "i"}},
            {"description":   {"$regex": search, "$options": "i"}},
        ]

    total = await count_documents(col, query)
    docs  = await get_documents(
        col,
        filter_query=query,
        skip=skip,
        limit=limit,
        sort=[("uploaded_at", DESCENDING)],
    )
    return docs, total


async def update_document_status(
    col:         AsyncIOMotorCollection,
    document_id: str,
    status:      DocumentStatus,
    error:       Optional[str] = None,
    extra:       Optional[dict] = None,
) -> None:
    """Update processing status (and optionally stats) of a document."""
    patch: dict = {
        "status":     status.value,
        "updated_at": utc_now(),
    }
    if error is not None:
        patch["processing_error"] = error
    if extra:
        patch.update(extra)

    await update_document(
        col,
        {"document_id": document_id},
        {"$set": patch},
    )


async def update_document_record(
    col:         AsyncIOMotorCollection,
    document_id: str,
    patch:       dict,
) -> bool:
    """Generic patch by document_id."""
    patch["updated_at"] = utc_now()
    return await update_document(
        col,
        {"document_id": document_id},
        {"$set": patch},
    )


async def delete_document_record(
    col:         AsyncIOMotorCollection,
    document_id: str,
) -> bool:
    """Hard-delete a document record by document_id."""
    return await delete_document(col, {"document_id": document_id})


async def get_categories(col: AsyncIOMotorCollection) -> list[str]:
    """Return all distinct category values in the collection."""
    try:
        cats = await col.distinct("category")
        return sorted(c for c in cats if c)
    except Exception as exc:
        logger.error("Failed to fetch categories: %s", exc)
        return []


# ── Chunk operations ──────────────────────────────────────────

async def save_chunks(
    col:    AsyncIOMotorCollection,
    chunks: list[TextChunk],
) -> list[str]:
    """
    Bulk-insert chunks into knowledge_chunks.
    Returns list of inserted _id strings.
    """
    if not chunks:
        return []

    now  = utc_now()
    ids  = []
    for ch in chunks:
        doc = {
            "chunk_id":       ch.chunk_id,
            "document_id":    ch.document_id,
            "chunk_index":    ch.chunk_index,
            "content":        ch.content,
            "char_count":     ch.char_count,
            "filename":       ch.filename,
            "original_name":  ch.original_name,
            "source":         ch.source,
            "category":       ch.category,
            "page_number":    ch.page_number,
            "uploaded_by":    ch.uploaded_by,
            "uploaded_at":    ch.uploaded_at,
            "is_embedded":    False,
            "embedding_model": None,
            "created_at":     now,
            "updated_at":     now,
        }
        inserted_id = await create_document(col, doc)
        ids.append(inserted_id)

    logger.info("Saved %d chunks for document %s", len(ids), chunks[0].document_id)
    return ids


async def mark_chunks_embedded(
    col:             AsyncIOMotorCollection,
    chunk_ids:       list[str],
    embedding_model: str,
) -> None:
    """Mark a batch of chunks as successfully embedded."""
    if not chunk_ids:
        return
    now = utc_now()
    await col.update_many(
        {"chunk_id": {"$in": chunk_ids}},
        {"$set": {
            "is_embedded":    True,
            "embedding_model": embedding_model,
            "updated_at":     now,
        }},
    )


async def delete_chunks_by_document_id(
    col:         AsyncIOMotorCollection,
    document_id: str,
) -> int:
    """Delete all chunks belonging to a document. Returns deleted count."""
    result = await col.delete_many({"document_id": document_id})
    logger.info(
        "Deleted %d chunks for document_id=%s",
        result.deleted_count, document_id,
    )
    return result.deleted_count


async def get_chunks_by_document_id(
    col:         AsyncIOMotorCollection,
    document_id: str,
    skip:        int = 0,
    limit:       int = 50,
) -> tuple[list[dict], int]:
    """Return paginated chunks for a document."""
    q     = {"document_id": document_id}
    total = await count_documents(col, q)
    docs  = await get_documents(
        col, filter_query=q,
        skip=skip, limit=limit,
        sort=[("chunk_index", 1)],
    )
    return docs, total
