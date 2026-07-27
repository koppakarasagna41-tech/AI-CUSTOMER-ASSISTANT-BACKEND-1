"""app/rag/schemas/response.py — RAG response schemas."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class SourceChunk(BaseModel):
    """A single retrieved knowledge chunk returned as a source reference."""
    chunk_id:      str
    document_id:   str
    filename:      str
    category:      str
    page_number:   Optional[int]   = None
    similarity:    float           # 0.0–1.0 (higher = more relevant)
    content_preview: str           # first 200 chars of chunk text


class RAGResponse(BaseModel):
    """
    Returned when confidence ≥ threshold.
    Contains the AI answer + source references.
    """
    conversation_id:  str
    question:         str
    answer:           str
    confidence_score: float
    sources:          list[SourceChunk]
    tokens_used:      int                 = 0
    model_used:       str                 = ""
    response_time_ms: float               = 0.0
    escalated:        bool                = False
    log_id:           Optional[str]       = None


class EscalationResponse(BaseModel):
    """
    Returned when confidence < threshold.
    """
    conversation_id:  str
    question:         str
    answer:           str           # the escalation message shown to user
    confidence_score: float
    escalated:        bool          = True
    escalation_id:    Optional[str] = None
    response_time_ms: float         = 0.0
    log_id:           Optional[str] = None


class HistoryMessageOut(BaseModel):
    """A single message in the conversation history."""
    id:         str
    role:       str
    content:    str
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class ConversationHistoryOut(BaseModel):
    """Full conversation history response."""
    conversation_id: str
    messages:        list[HistoryMessageOut]
    total:           int
