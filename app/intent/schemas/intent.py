"""
app/intent/schemas/intent.py
──────────────────────────────
Pydantic request / response schemas for Intent Detection endpoints.
"""

from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


# ── Request schemas ───────────────────────────────────────────

class IntentRequest(BaseModel):
    """Body for POST /intent/detect"""
    message:         str           = Field(
        ..., min_length=1, max_length=2000,
        examples=["My payment keeps failing"],
    )
    conversation_id: Optional[str] = Field(
        None,
        description="Link this detection to an existing conversation.",
    )


class IntentBatchRequest(BaseModel):
    """Body for POST /intent/detect/batch — classify multiple messages at once."""
    messages:        list[str]     = Field(
        ..., min_items=1, max_items=20,
        examples=[["Hi!", "I want a refund", "The app crashed"]],
    )
    conversation_id: Optional[str] = None


# ── Response schemas ──────────────────────────────────────────

class IntentScore(BaseModel):
    """A single intent with its probability score."""
    intent:     str
    label:      str
    score:      float = Field(..., ge=0.0, le=1.0)


class IntentResult(BaseModel):
    """
    Returned from POST /intent/detect.
    Contains the top intent + full score distribution.
    """
    message:         str
    intent:          str            # winning intent label
    label:           str            # human-readable label
    confidence:      float          # winning score  (0.0 – 1.0)
    is_confident:    bool           # True if confidence ≥ threshold
    all_scores:      list[IntentScore]
    prompt_category: str            # maps to a prompt template category
    model_used:      str
    tokens_used:     int            = 0
    latency_ms:      float          = 0.0
    intent_id:       Optional[str]  = None   # MongoDB document ID (when saved)
    conversation_id: Optional[str]  = None


class IntentLogOut(BaseModel):
    """Stored intent log record returned from GET /intent/logs."""
    id:              str
    intent_id:       str
    conversation_id: Optional[str]  = None
    user_id:         Optional[str]  = None
    message:         str
    intent:          str
    confidence:      float
    all_scores:      dict[str, float] = {}
    model_used:      Optional[str]  = None
    tokens_used:     Optional[int]  = None
    is_fallback:     bool           = False
    latency_ms:      Optional[float] = None
    created_at:      Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class IntentBatchResult(BaseModel):
    """Returned from POST /intent/detect/batch."""
    results: list[IntentResult]
    total:   int
