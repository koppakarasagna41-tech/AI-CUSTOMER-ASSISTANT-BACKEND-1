"""
app/history/schemas/history.py
────────────────────────────────
Rich conversation history schemas.

MessageHistoryItem     — single message with intent + sentiment enrichment
ConversationHistory    — full conversation record with all messages embedded
ConversationHistoryList — summary record for list views
HistorySearchParams    — search / filter / sort parameters
"""

from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


# ── Per-message enrichment ────────────────────────────────────

class MessageIntentOut(BaseModel):
    intent:      Optional[str]   = None
    label:       Optional[str]   = None
    confidence:  Optional[float] = None


class MessageSentimentOut(BaseModel):
    sentiment:     Optional[str]   = None
    label:         Optional[str]   = None
    emoji:         Optional[str]   = None
    confidence:    Optional[float] = None
    polarity_score: Optional[float] = None


class MessageHistoryItem(BaseModel):
    """A single message inside a conversation history record."""
    id:              str
    conversation_id: str
    role:            str                         # user | assistant | system
    content:         str
    status:          Optional[str]   = None
    tokens_used:     Optional[int]   = None
    model_used:      Optional[str]   = None
    intent:          Optional[MessageIntentOut]     = None
    sentiment:       Optional[MessageSentimentOut]  = None
    created_at:      Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


# ── Conversation-level enrichment ─────────────────────────────

class ConversationSentimentSummary(BaseModel):
    dominant:        Optional[str]   = None
    dominant_label:  Optional[str]   = None
    emoji:           Optional[str]   = None
    avg_polarity:    Optional[float] = None
    trend:           Optional[str]   = None


class LinkedTicket(BaseModel):
    ticket_id:  str
    subject:    str
    category:   str
    priority:   str
    status:     str


class ConversationHistory(BaseModel):
    """Full conversation history — all messages + enrichment."""
    id:              str
    conversation_id: str
    user_id:         Optional[str]                     = None
    title:           Optional[str]                     = None
    status:          str
    message_count:   int                               = 0
    last_message_at: Optional[str]                     = None
    tags:            list[str]                         = []

    # Enrichment
    sentiment_summary: Optional[ConversationSentimentSummary] = None
    linked_tickets:    list[LinkedTicket]              = []

    # Messages (paginated)
    messages:          list[MessageHistoryItem]        = []
    messages_total:    int                             = 0
    messages_page:     int                             = 1
    messages_page_size: int                            = 50

    created_at:      Optional[datetime] = None
    updated_at:      Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class ConversationHistoryList(BaseModel):
    """Summary record for list/search responses (no embedded messages)."""
    id:              str
    conversation_id: str
    user_id:         Optional[str]   = None
    title:           Optional[str]   = None
    status:          str
    message_count:   int             = 0
    last_message_at: Optional[str]   = None
    tags:            list[str]       = []
    sentiment:       Optional[str]   = None
    sentiment_polarity: Optional[float] = None
    sentiment_trend: Optional[str]   = None
    has_tickets:     bool            = False
    ticket_count:    int             = 0
    created_at:      Optional[datetime] = None
    updated_at:      Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


# ── Search / filter parameters ────────────────────────────────

class HistorySearchParams(BaseModel):
    """Query parameters for GET /history."""
    search:    Optional[str]  = Field(None, description="Search title, tags, message content")
    status:    Optional[str]  = None
    sentiment: Optional[str]  = None
    user_id:   Optional[str]  = None
    date_from: Optional[datetime] = None
    date_to:   Optional[datetime] = None
    has_tickets: Optional[bool]  = None
    sort_by:   str            = Field("created_at", description="created_at | updated_at | message_count | sentiment_polarity")
    sort_order: str           = Field("desc", description="asc | desc")


class HistoryDeleteResult(BaseModel):
    """Returned from DELETE operations."""
    conversation_id:   str
    deleted_messages:  int
    deleted_sentiment: int
    deleted_intent:    int
