"""
app/database/mongodb.py
────────────────────────
Async MongoDB connection manager using Motor.

Responsibilities:
  1. Lifecycle — connect_to_mongo() / close_mongo_connection()
     called from the FastAPI lifespan context manager in main.py.

  2. Index creation — ensure_indexes() creates all required indexes
     at startup so they exist before any request is served.

  3. Accessors — get_database() / get_collection() are thin helpers
     used by services and overridden in tests.

  4. Health probe — ping_database() used by /health endpoint.

Collections & indexes created:
  users          — email (unique)
  conversations  — conversation_id, user_id, status, created_at
  messages       — conversation_id, created_at
  tickets        — ticket_id (unique), user_id, status, created_at
  analytics      — event_type, created_at
"""

import logging
from typing import Optional

from motor.motor_asyncio import (
    AsyncIOMotorClient,
    AsyncIOMotorDatabase,
    AsyncIOMotorCollection,
)
from pymongo import ASCENDING, DESCENDING, IndexModel
from pymongo.errors import ConnectionFailure, OperationFailure, ServerSelectionTimeoutError

from app.config import settings
from app.core.exceptions import DatabaseError

logger = logging.getLogger(__name__)

# ── Internal state ────────────────────────────────────────────
_db_state: dict = {
    "client": None,
    "db":     None,
}

# ── Collection names ─────────────────────────────────────────
COLLECTIONS = {
    "users":         "users",
    "conversations": "conversations",
    "messages":      "messages",
    "tickets":       "tickets",
    "analytics":     "analytics",
}


# ── Index definitions ─────────────────────────────────────────

def _index_definitions() -> dict[str, list[IndexModel]]:
    """
    Return all IndexModel definitions keyed by collection name.
    Centralising them here makes it easy to add/remove indexes
    without hunting across multiple files.
    """
    return {
        "users": [
            IndexModel([("email", ASCENDING)], unique=True, name="email_unique"),
            IndexModel([("created_at", DESCENDING)],         name="created_at_desc"),
        ],
        "conversations": [
            IndexModel([("conversation_id", ASCENDING)],     name="conversation_id"),
            IndexModel([("user_id",          ASCENDING)],    name="user_id"),
            IndexModel([("status",           ASCENDING)],    name="status"),
            IndexModel([("created_at",       DESCENDING)],   name="created_at_desc"),
            # Compound index for common list query pattern
            IndexModel(
                [("user_id", ASCENDING), ("status", ASCENDING), ("created_at", DESCENDING)],
                name="user_status_date",
            ),
        ],
        "messages": [
            IndexModel([("conversation_id", ASCENDING)],     name="conversation_id"),
            IndexModel([("created_at",      DESCENDING)],    name="created_at_desc"),
            # Compound for fetching messages of a conversation sorted by time
            IndexModel(
                [("conversation_id", ASCENDING), ("created_at", ASCENDING)],
                name="conv_messages_sorted",
            ),
        ],
        "tickets": [
            IndexModel([("ticket_id",  ASCENDING)], unique=True, name="ticket_id_unique"),
            IndexModel([("user_id",    ASCENDING)],              name="user_id"),
            IndexModel([("status",     ASCENDING)],              name="status"),
            IndexModel([("created_at", DESCENDING)],             name="created_at_desc"),
        ],
        "analytics": [
            IndexModel([("event_type", ASCENDING)],              name="event_type"),
            IndexModel([("created_at", DESCENDING)],             name="created_at_desc"),
            IndexModel(
                [("created_at", ASCENDING)],
                expireAfterSeconds=90 * 24 * 3600,
                name="analytics_ttl_90d",
            ),
        ],
        # ── Knowledge Base ────────────────────────────────────
        "knowledge_documents": [
            IndexModel([("document_id", ASCENDING)], unique=True, name="document_id_unique"),
            IndexModel([("filename",    ASCENDING)],              name="filename"),
            IndexModel([("category",    ASCENDING)],              name="category"),
            IndexModel([("uploaded_by", ASCENDING)],              name="uploaded_by"),
            IndexModel([("uploaded_at", DESCENDING)],             name="uploaded_at_desc"),
            IndexModel([("status",      ASCENDING)],              name="status"),
        ],
        "knowledge_chunks": [
            IndexModel([("document_id",  ASCENDING)],  name="document_id"),
            IndexModel([("chunk_index",  ASCENDING)],  name="chunk_index"),
            IndexModel([("category",     ASCENDING)],  name="category"),
            IndexModel([("created_at",   DESCENDING)], name="created_at_desc"),
            IndexModel(
                [("document_id", ASCENDING), ("chunk_index", ASCENDING)],
                name="doc_chunk_compound",
            ),
        ],
        # ── RAG ──────────────────────────────────────────────
        "retrieval_logs": [
            IndexModel([("log_id",           ASCENDING)], unique=True, name="log_id_unique"),
            IndexModel([("conversation_id",  ASCENDING)],              name="conversation_id"),
            IndexModel([("user_id",          ASCENDING)],              name="user_id"),
            IndexModel([("escalation_status", ASCENDING)],             name="escalation_status"),
            IndexModel([("created_at",       DESCENDING)],             name="created_at_desc"),
        ],
        "escalations": [
            IndexModel([("escalation_id",   ASCENDING)], unique=True, name="escalation_id_unique"),
            IndexModel([("conversation_id", ASCENDING)],              name="conversation_id"),
            IndexModel([("user_id",         ASCENDING)],              name="user_id"),
            IndexModel([("state",           ASCENDING)],              name="state"),
            IndexModel([("created_at",      DESCENDING)],             name="created_at_desc"),
        ],
        # ── Intent Detection ─────────────────────────────────
        "intent_logs": [
            IndexModel([("intent_id",       ASCENDING)], unique=True, name="intent_id_unique"),
            IndexModel([("conversation_id", ASCENDING)],              name="conversation_id"),
            IndexModel([("user_id",         ASCENDING)],              name="user_id"),
            IndexModel([("intent",          ASCENDING)],              name="intent"),
            IndexModel([("created_at",      DESCENDING)],             name="created_at_desc"),
        ],
        # ── Sentiment Analysis ────────────────────────────────
        "sentiment_logs": [
            IndexModel([("sentiment_id",    ASCENDING)], unique=True, name="sentiment_id_unique"),
            IndexModel([("conversation_id", ASCENDING)],              name="conversation_id"),
            IndexModel([("message_id",      ASCENDING)],              name="message_id"),
            IndexModel([("user_id",         ASCENDING)],              name="user_id"),
            IndexModel([("sentiment",       ASCENDING)],              name="sentiment"),
            IndexModel([("created_at",      DESCENDING)],             name="created_at_desc"),
        ],
        # ── Escalation Detection ─────────────────────────────
        "escalation_events": [
            IndexModel([("escalation_id",   ASCENDING)], unique=True, name="escalation_id_unique"),
            IndexModel([("conversation_id", ASCENDING)],              name="conversation_id"),
            IndexModel([("ticket_id",       ASCENDING)],              name="ticket_id"),
            IndexModel([("user_id",         ASCENDING)],              name="user_id"),
            IndexModel([("trigger",         ASCENDING)],              name="trigger"),
            IndexModel([("state",           ASCENDING)],              name="state"),
            IndexModel([("created_at",      DESCENDING)],             name="created_at_desc"),
        ],
    }


async def ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    """
    Create all indexes in all collections.
    Uses `create_indexes()` which is idempotent — safe to call on every startup.
    Logs a warning (not an error) if an index already exists with different options.
    """
    definitions = _index_definitions()
    for col_name, indexes in definitions.items():
        try:
            collection = db[col_name]
            result = await collection.create_indexes(indexes)
            logger.info(
                "Indexes ensured — collection=%s created/confirmed=%s",
                col_name,
                result,
            )
        except OperationFailure as exc:
            # Non-fatal: might happen if an index exists with different options
            # in an existing Atlas cluster.  Warn and continue.
            logger.warning(
                "Index creation warning — collection=%s | %s",
                col_name,
                exc,
            )


# ── Lifecycle ─────────────────────────────────────────────────

async def connect_to_mongo() -> None:
    """
    Open the Motor client, verify connectivity, and create indexes.
    Called from the FastAPI lifespan startup hook in main.py.
    """
    logger.info("Connecting to MongoDB Atlas…")
    try:
        client: AsyncIOMotorClient = AsyncIOMotorClient(
            settings.MONGODB_URL,
            serverSelectionTimeoutMS=5_000,
            connectTimeoutMS=10_000,
            socketTimeoutMS=10_000,
            maxIdleTimeMS=45_000,       # keep-alive for Atlas free tier
            maxPoolSize=10,
            minPoolSize=1,
        )

        # Force a real network call before storing the client
        await client.admin.command("ping")

        db = client[settings.MONGODB_DB_NAME]
        _db_state["client"] = client
        _db_state["db"]     = db

        logger.info("MongoDB connected — database: %s", settings.MONGODB_DB_NAME)

        # Create indexes after confirming connectivity
        await ensure_indexes(db)

    except (ConnectionFailure, ServerSelectionTimeoutError) as exc:
        logger.critical("MongoDB connection failed: %s", exc)
        raise


async def close_mongo_connection() -> None:
    """
    Close the Motor client gracefully.
    Called from the FastAPI lifespan shutdown hook in main.py.
    """
    client: Optional[AsyncIOMotorClient] = _db_state.get("client")
    if client:
        client.close()
        _db_state["client"] = None
        _db_state["db"]     = None
        logger.info("MongoDB connection closed.")


# ── Accessors ─────────────────────────────────────────────────

def get_database() -> AsyncIOMotorDatabase:
    """
    Return the active database handle.
    Raises DatabaseError if the database is unavailable.
    """
    db = _db_state.get("db")
    if db is None:
        raise DatabaseError(
            message="Database is unavailable. Please try again later.",
            error_code="DATABASE_UNAVAILABLE",
            details={"service": "mongodb"},
        )
    return db


def get_collection(name: str) -> AsyncIOMotorCollection:
    """
    Return a named collection from the active database.

    Usage in a service:
        col = get_collection("tickets")
        doc = await col.find_one({"ticket_id": tid})
    """
    return get_database()[name]


# ── Health probe ──────────────────────────────────────────────

async def ping_database() -> bool:
    """
    Lightweight ping to Atlas — used by the /health endpoint.
    Returns True on success, False on any error (never raises).
    """
    try:
        client: Optional[AsyncIOMotorClient] = _db_state.get("client")
        if client is None:
            return False
        await client.admin.command("ping")
        return True
    except Exception as exc:          # noqa: BLE001
        logger.warning("MongoDB ping failed: %s", exc)
        return False
