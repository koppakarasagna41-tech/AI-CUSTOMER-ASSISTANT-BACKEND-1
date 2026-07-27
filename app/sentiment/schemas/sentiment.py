"""app/sentiment/schemas/sentiment.py — Request/response schemas."""

from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


# ── Request ────────────────────────────────────────────────────

class SentimentRequest(BaseModel):
    """POST /sentiment/analyze — analyse a single text."""
    text:            str           = Field(..., min_length=1, max_length=5000,
                                           examples=["This service is absolutely terrible!"])
    conversation_id: Optional[str] = None
    message_id:      Optional[str] = None
    source:          str           = "message"


class SentimentBatchRequest(BaseModel):
    """POST /sentiment/analyze/batch — analyse up to 20 texts."""
    texts:           list[str]     = Field(..., min_items=1, max_items=20)
    conversation_id: Optional[str] = None


class ConversationSentimentRequest(BaseModel):
    """POST /sentiment/conversation/{id} — full conversation sentiment."""
    conversation_id: str


# ── Response ───────────────────────────────────────────────────

class SentimentScore(BaseModel):
    sentiment:  str
    label:      str
    score:      float
    emoji:      str


class SentimentResult(BaseModel):
    """Returned from POST /sentiment/analyze."""
    text:            str
    sentiment:       str           # winning label
    label:           str           # human-readable
    emoji:           str
    confidence:      float
    polarity_score:  float         # -2.0 to +1.0
    is_confident:    bool
    all_scores:      list[SentimentScore]
    model_used:      str
    tokens_used:     int           = 0
    latency_ms:      float         = 0.0
    sentiment_id:    Optional[str] = None
    conversation_id: Optional[str] = None
    message_id:      Optional[str] = None


class ConversationSentimentOut(BaseModel):
    """Aggregated sentiment for a full conversation."""
    conversation_id:    str
    total_messages:     int
    dominant_sentiment: str
    dominant_label:     str
    dominant_emoji:     str
    average_polarity:   float
    distribution:       dict[str, int]     # sentiment → count
    trend:              str                # "improving" | "declining" | "stable"
    messages:           list[SentimentResult] = []


class SentimentLogOut(BaseModel):
    """Stored sentiment log record."""
    id:              str
    sentiment_id:    str
    conversation_id: Optional[str]      = None
    message_id:      Optional[str]      = None
    user_id:         Optional[str]      = None
    text:            str
    source:          str                = "message"
    sentiment:       str
    confidence:      float
    polarity_score:  float
    all_scores:      dict[str, float]   = {}
    model_used:      Optional[str]      = None
    tokens_used:     Optional[int]      = None
    is_fallback:     bool               = False
    latency_ms:      Optional[float]    = None
    created_at:      Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class SentimentBatchResult(BaseModel):
    results:    list[SentimentResult]
    total:      int
    summary:    dict[str, int]        # sentiment → count across batch
