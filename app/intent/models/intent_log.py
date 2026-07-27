"""
app/intent/models/intent_log.py
─────────────────────────────────
MongoDB document model for the `intent_logs` collection.
Stores every intent detection result for observability and analytics.
"""

from datetime import datetime
from typing import Optional
from pydantic import Field
from app.models.base import MongoBaseModel, TimestampMixin


class IntentLog(MongoBaseModel, TimestampMixin):
    """Stored in the `intent_logs` MongoDB collection."""

    intent_id:        str                    # ILD-YYYYMMDD-XXXXXXXX
    conversation_id:  Optional[str] = None   # linked conversation
    user_id:          Optional[str] = None   # authenticated user

    # Input
    message:          str                    # original customer message

    # Classification result
    intent:           str                    # detected intent label
    confidence:       float                  # 0.0 – 1.0
    all_scores:       dict[str, float] = Field(default_factory=dict)  # all intent scores

    # Meta
    model_used:       Optional[str] = None
    tokens_used:      Optional[int] = None
    is_fallback:      bool = False           # True when confidence < threshold
    latency_ms:       Optional[float] = None
