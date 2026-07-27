"""
app/sentiment/models/sentiment_log.py
───────────────────────────────────────
MongoDB document model for the `sentiment_logs` collection.
One record per analysed message (or per conversation summary).
"""

from typing import Optional
from pydantic import Field
from app.models.base import MongoBaseModel, TimestampMixin


class SentimentLog(MongoBaseModel, TimestampMixin):
    """Stored in the `sentiment_logs` MongoDB collection."""

    sentiment_id:     str                          # SID-YYYYMMDD-XXXXXXXX
    conversation_id:  Optional[str] = None
    message_id:       Optional[str] = None         # links to messages._id
    user_id:          Optional[str] = None

    # Input
    text:             str                          # analysed text (message content)
    source:           str = "message"              # "message" | "conversation_summary"

    # Classification result
    sentiment:        str                          # winning label
    confidence:       float                        # 0.0 – 1.0
    polarity_score:   float                        # numeric polarity (-2 to +1)
    all_scores:       dict[str, float] = Field(default_factory=dict)

    # Meta
    model_used:       Optional[str]  = None
    tokens_used:      Optional[int]  = None
    is_fallback:      bool           = False
    latency_ms:       Optional[float] = None
