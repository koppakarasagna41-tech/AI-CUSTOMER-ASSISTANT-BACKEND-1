"""
app/rag/models/retrieval_log.py
─────────────────────────────────
MongoDB document model for the `retrieval_logs` collection.
Records every RAG query for observability and debugging.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import Field

from app.models.base import MongoBaseModel, TimestampMixin


class EscalationStatus(str, Enum):
    NOT_ESCALATED = "not_escalated"
    ESCALATED     = "escalated"
    PENDING       = "pending"


class RetrievalLog(MongoBaseModel, TimestampMixin):
    """Stored in `retrieval_logs` collection."""

    log_id:                str
    conversation_id:       str
    user_id:               Optional[str]  = None

    # Query
    customer_question:     str
    query_embedding_dims:  Optional[int]  = None

    # Retrieval results
    retrieved_chunks:      int            = 0
    retrieved_document_ids: list[str]     = Field(default_factory=list)
    top_similarity_score:  Optional[float] = None
    avg_similarity_score:  Optional[float] = None

    # Generation
    ai_response:           Optional[str]  = None
    confidence_score:      Optional[float] = None
    model_used:            Optional[str]  = None
    tokens_used:           Optional[int]  = None

    # Timing
    response_time_ms:      Optional[float] = None

    # Escalation
    escalation_status:     EscalationStatus = EscalationStatus.NOT_ESCALATED
    escalation_id:         Optional[str]   = None
