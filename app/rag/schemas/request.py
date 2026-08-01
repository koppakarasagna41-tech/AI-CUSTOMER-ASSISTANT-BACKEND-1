"""app/rag/schemas/request.py — RAG request schemas."""

from typing import Optional
from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    """
    POST /rag/query
    Full RAG query — creates a new conversation or continues an existing one.
    """
    question:        str           = Field(
        ..., min_length=1, max_length=2000,
        examples=["How do I reset my password?"]
    )
    conversation_id: Optional[str] = Field(
        None,
        description="Existing conversation ID. Omit to start a new one.",
    )
    top_k:           Optional[int] = Field(
        None, ge=1, le=20,
        description="Override number of chunks to retrieve (default from settings).",
    )


class AskRequest(BaseModel):
    """
    POST /rag/ask
    Single-shot question — no conversation history, no persistence.
    Useful for quick lookups or testing.
    """
    question: str = Field(
        ..., min_length=1, max_length=2000,
        examples=["What is your refund policy?"]
    )
    top_k:    Optional[int] = Field(
        None, ge=1, le=20,
    )
