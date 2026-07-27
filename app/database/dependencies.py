"""
app/database/dependencies.py
──────────────────────────────
FastAPI dependency functions for database access.

Inject via Depends() in any route handler or service:

    from app.database.dependencies import get_db, UsersCollection

    @router.get("/users/{user_id}")
    async def get_user(
        user_id: str,
        col: AsyncIOMotorCollection = Depends(UsersCollection),
    ):
        doc = await get_document_by_id(col, user_id)
        ...
"""

from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorDatabase
from fastapi import Depends

from app.database.mongodb import get_database


# ── Base DB dependency ────────────────────────────────────────

async def get_db() -> AsyncIOMotorDatabase:
    """Yield the active Motor database handle."""
    yield get_database()


# ── Collection dependency factory ─────────────────────────────

def get_col(collection_name: str):
    """
    Factory that returns a FastAPI dependency for a specific collection.

    Usage:
        MyCol = get_col("my_collection")

        @router.get("/")
        async def handler(col: AsyncIOMotorCollection = Depends(MyCol)):
            ...
    """
    async def _dep(
        db: AsyncIOMotorDatabase = Depends(get_db),
    ) -> AsyncIOMotorCollection:
        yield db[collection_name]

    # Give the inner function a readable name for FastAPI's dependency graph
    _dep.__name__ = f"get_{collection_name}_collection"
    return _dep


# ── Pre-built collection dependencies ────────────────────────
# Import these directly in routers/services instead of calling get_col() again.

UsersCollection         = get_col("users")
ConversationsCollection = get_col("conversations")
MessagesCollection      = get_col("messages")
TicketsCollection       = get_col("tickets")
AnalyticsCollection     = get_col("analytics")
KnowledgeDocumentsCollection = get_col("knowledge_documents")
KnowledgeChunksCollection    = get_col("knowledge_chunks")
IntentLogsCollection         = get_col("intent_logs")
SentimentLogsCollection      = get_col("sentiment_logs")
EscalationEventsCollection   = get_col("escalation_events")
