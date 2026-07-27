# app/database package — public API
from .mongodb import (
    connect_to_mongo,
    close_mongo_connection,
    get_database,
    get_collection,
    ping_database,
    ensure_indexes,
    COLLECTIONS,
)
from .dependencies import (
    get_db,
    get_col,
    ConversationsCollection,
    UsersCollection,
    MessagesCollection,
    TicketsCollection,
    AnalyticsCollection,
    KnowledgeDocumentsCollection,
    KnowledgeChunksCollection,
    IntentLogsCollection,
    SentimentLogsCollection,
    EscalationEventsCollection,
)
from .crud import (
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

__all__ = [
    # Lifecycle
    "connect_to_mongo",
    "close_mongo_connection",
    "ensure_indexes",
    "COLLECTIONS",
    # Accessors
    "get_database",
    "get_collection",
    "ping_database",
    # FastAPI dependencies
    "get_db",
    "get_col",
    "ConversationsCollection",
    "UsersCollection",
    "MessagesCollection",
    "TicketsCollection",
    "AnalyticsCollection",
    "KnowledgeDocumentsCollection",
    "KnowledgeChunksCollection",
    "IntentLogsCollection",
    "SentimentLogsCollection",
    "EscalationEventsCollection",
    # CRUD helpers
    "create_document",
    "get_document",
    "get_document_by_id",
    "get_documents",
    "count_documents",
    "update_document",
    "update_document_by_id",
    "delete_document",
    "delete_document_by_id",
    "document_exists",
]
