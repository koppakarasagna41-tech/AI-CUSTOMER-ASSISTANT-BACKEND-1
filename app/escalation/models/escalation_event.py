"""
app/escalation/models/escalation_event.py
──────────────────────────────────────────
MongoDB document model for the `escalation_events` collection.

This is distinct from the RAG escalation model (app/rag/models/escalation.py).
That model handles low-confidence RAG responses.
This model handles full conversation escalation detection events.
"""

from datetime import datetime
from typing import Optional
from pydantic import Field
from app.models.base import MongoBaseModel, TimestampMixin


class EscalationEvent(MongoBaseModel, TimestampMixin):
    """Stored in the `escalation_events` MongoDB collection."""

    escalation_id:   str                   # ESC-YYYYMMDD-XXXXXXXX

    # Linked entities
    conversation_id: str
    user_id:         Optional[str] = None
    ticket_id:       Optional[str] = None  # auto-generated escalation ticket

    # Detection result
    trigger:         str                   # EscalationTrigger value
    priority:        str                   # EscalationPriority value
    description:     str                   # human-readable reason
    state:           str = "open"          # EscalationState value

    # Evidence collected during detection
    evidence:        dict = Field(default_factory=dict)
    # e.g. {
    #   "sentiment": "very_negative",
    #   "polarity_score": -2.0,
    #   "negative_streak": 3,
    #   "trigger_message": "I want to cancel everything",
    #   "unanswered_count": 4,
    # }

    # Resolution
    assigned_to:     Optional[str]      = None   # agent user_id
    resolved_at:     Optional[datetime] = None
    resolution_note: Optional[str]      = None

    # Notification status
    admin_notified:  bool               = False
    notified_at:     Optional[datetime] = None
