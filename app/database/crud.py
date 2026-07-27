"""
app/database/crud.py
─────────────────────
Reusable async CRUD helper functions for Motor collections.

These are intentionally thin wrappers — they handle:
  - ObjectId conversion (str → BSON ObjectId)
  - Consistent logging
  - Raising DatabaseError on unexpected exceptions
  - Returning None (not raising) for "not found" cases

Services call these helpers and apply their own business logic on top.
Never put business rules in this layer.

Functions
─────────
create_document(collection, data)               → inserted_id (str)
get_document(collection, filter)                → dict | None
get_document_by_id(collection, doc_id)          → dict | None
get_documents(collection, filter, skip, limit, sort) → list[dict]
count_documents(collection, filter)             → int
update_document(collection, filter, update)     → bool
update_document_by_id(collection, doc_id, update) → bool
delete_document(collection, filter)             → bool
delete_document_by_id(collection, doc_id)       → bool
document_exists(collection, filter)             → bool
"""

import logging
from typing import Any, Optional

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorCollection
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.core.exceptions import ConflictError, DatabaseError

logger = logging.getLogger(__name__)


# ── Internal helpers ──────────────────────────────────────────

def _to_object_id(doc_id: str) -> ObjectId:
    """Convert a string to a BSON ObjectId, raising ValueError on invalid input."""
    try:
        return ObjectId(doc_id)
    except (InvalidId, TypeError) as exc:
        raise ValueError(f"Invalid document ID: {doc_id!r}") from exc


def _serialize(doc: Optional[dict]) -> Optional[dict]:
    """
    Convert ObjectId fields to strings in a returned document so
    they can be fed into Pydantic models without extra handling.
    """
    if doc is None:
        return None
    if "_id" in doc and isinstance(doc["_id"], ObjectId):
        doc["_id"] = str(doc["_id"])
    return doc


# ── CRUD ──────────────────────────────────────────────────────

async def create_document(
    collection: AsyncIOMotorCollection,
    data: dict[str, Any],
) -> str:
    """
    Insert a single document and return its string _id.

    Raises:
        ConflictError  — on DuplicateKeyError (unique index violation)
        DatabaseError  — on any other PyMongo error
    """
    try:
        result = await collection.insert_one(data)
        inserted_id = str(result.inserted_id)
        logger.info(
            "create_document completed",
            extra={"component": "mongodb", "event": "create_document", "collection": collection.name, "document_id": inserted_id},
        )
        return inserted_id
    except DuplicateKeyError as exc:
        logger.warning(
            "DuplicateKeyError | collection=%s | %s",
            collection.name, exc.details,
        )
        raise ConflictError(
            message="A document with this key already exists.",
            error_code="DUPLICATE_KEY",
            details=exc.details,
        ) from exc
    except PyMongoError as exc:
        logger.error("create_document failed | collection=%s | %s", collection.name, exc)
        raise DatabaseError(
            message="Failed to create document.",
            error_code="DB_CREATE_ERROR",
        ) from exc


async def get_document(
    collection: AsyncIOMotorCollection,
    filter_query: dict[str, Any],
    projection: Optional[dict] = None,
) -> Optional[dict]:
    """
    Find and return a single document matching filter_query.
    Returns None if not found (does not raise).
    """
    try:
        doc = await collection.find_one(filter_query, projection)
        logger.info(
            "get_document completed",
            extra={"component": "mongodb", "event": "read_document", "collection": collection.name, "found": doc is not None},
        )
        return _serialize(doc)
    except PyMongoError as exc:
        logger.error("get_document failed | collection=%s | %s", collection.name, exc)
        raise DatabaseError(
            message="Failed to retrieve document.",
            error_code="DB_READ_ERROR",
        ) from exc


async def get_document_by_id(
    collection: AsyncIOMotorCollection,
    doc_id: str,
    projection: Optional[dict] = None,
) -> Optional[dict]:
    """
    Find a document by its _id string.
    Returns None if the id is invalid or the document is not found.
    """
    try:
        oid = _to_object_id(doc_id)
    except ValueError:
        return None

    return await get_document(collection, {"_id": oid}, projection)


async def get_documents(
    collection: AsyncIOMotorCollection,
    filter_query: dict[str, Any] = None,
    skip: int = 0,
    limit: int = 20,
    sort: Optional[list[tuple[str, int]]] = None,
    projection: Optional[dict] = None,
) -> list[dict]:
    """
    Return a list of documents matching filter_query with pagination.

    Args:
        filter_query : MongoDB filter dict (default: {} → all documents)
        skip         : number of documents to skip (offset)
        limit        : maximum documents to return (default 20, max 100)
        sort         : list of (field, direction) tuples, e.g. [("created_at", -1)]
        projection   : fields to include/exclude

    Returns:
        List of serialised document dicts.
    """
    filter_query = filter_query or {}
    limit = min(limit, 100)   # hard cap to prevent runaway queries

    try:
        cursor = collection.find(filter_query, projection)
        if sort:
            cursor = cursor.sort(sort)
        cursor = cursor.skip(skip).limit(limit)

        docs = await cursor.to_list(length=limit)
        logger.info(
            "get_documents completed",
            extra={"component": "mongodb", "event": "read_documents", "collection": collection.name, "documents_count": len(docs)},
        )
        return [_serialize(doc) for doc in docs]
    except PyMongoError as exc:
        logger.error("get_documents failed | collection=%s | %s", collection.name, exc)
        raise DatabaseError(
            message="Failed to retrieve documents.",
            error_code="DB_READ_ERROR",
        ) from exc


async def count_documents(
    collection: AsyncIOMotorCollection,
    filter_query: dict[str, Any] = None,
) -> int:
    """Return the count of documents matching filter_query."""
    filter_query = filter_query or {}
    try:
        count = await collection.count_documents(filter_query)
        logger.info(
            "count_documents completed",
            extra={"component": "mongodb", "event": "count_documents", "collection": collection.name, "count": count},
        )
        return count
    except PyMongoError as exc:
        logger.error("count_documents failed | collection=%s | %s", collection.name, exc)
        raise DatabaseError(
            message="Failed to count documents.",
            error_code="DB_COUNT_ERROR",
        ) from exc


async def update_document(
    collection: AsyncIOMotorCollection,
    filter_query: dict[str, Any],
    update_data: dict[str, Any],
    upsert: bool = False,
) -> bool:
    """
    Update the first document matching filter_query.

    update_data should be a MongoDB update expression, e.g.:
        {"$set": {"status": "resolved"}, "$currentDate": {"updated_at": True}}

    Returns True if a document was modified (or upserted), False otherwise.
    """
    try:
        result = await collection.update_one(filter_query, update_data, upsert=upsert)
        matched = result.matched_count > 0 or result.upserted_id is not None
        logger.info(
            "update_document completed",
            extra={"component": "mongodb", "event": "update_document", "collection": collection.name, "matched": matched, "modified": result.modified_count > 0},
        )
        return matched
    except DuplicateKeyError as exc:
        raise ConflictError(
            message="Update would create a duplicate key.",
            error_code="DUPLICATE_KEY",
            details=exc.details,
        ) from exc
    except PyMongoError as exc:
        logger.error("update_document failed | collection=%s | %s", collection.name, exc)
        raise DatabaseError(
            message="Failed to update document.",
            error_code="DB_UPDATE_ERROR",
        ) from exc


async def update_document_by_id(
    collection: AsyncIOMotorCollection,
    doc_id: str,
    update_data: dict[str, Any],
) -> bool:
    """
    Update a document by its _id string.
    Returns False if the id is invalid or no document matched.
    """
    try:
        oid = _to_object_id(doc_id)
    except ValueError:
        return False

    return await update_document(collection, {"_id": oid}, update_data)


async def delete_document(
    collection: AsyncIOMotorCollection,
    filter_query: dict[str, Any],
) -> bool:
    """
    Delete the first document matching filter_query.
    Returns True if a document was deleted, False if nothing matched.
    """
    try:
        result = await collection.delete_one(filter_query)
        deleted = result.deleted_count > 0
        logger.info(
            "delete_document completed",
            extra={"component": "mongodb", "event": "delete_document", "collection": collection.name, "deleted": deleted},
        )
        return deleted
    except PyMongoError as exc:
        logger.error("delete_document failed | collection=%s | %s", collection.name, exc)
        raise DatabaseError(
            message="Failed to delete document.",
            error_code="DB_DELETE_ERROR",
        ) from exc


async def delete_document_by_id(
    collection: AsyncIOMotorCollection,
    doc_id: str,
) -> bool:
    """
    Delete a document by its _id string.
    Returns False if the id is invalid or no document matched.
    """
    try:
        oid = _to_object_id(doc_id)
    except ValueError:
        return False

    return await delete_document(collection, {"_id": oid})


async def document_exists(
    collection: AsyncIOMotorCollection,
    filter_query: dict[str, Any],
) -> bool:
    """
    Return True if at least one document matches filter_query.
    Uses count_documents with limit=1 for efficiency.
    """
    try:
        count = await collection.count_documents(filter_query, limit=1)
        return count > 0
    except PyMongoError as exc:
        logger.error("document_exists failed | collection=%s | %s", collection.name, exc)
        raise DatabaseError(
            message="Failed to check document existence.",
            error_code="DB_EXISTS_ERROR",
        ) from exc
