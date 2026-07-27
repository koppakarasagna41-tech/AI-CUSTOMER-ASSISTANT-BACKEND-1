"""
app/rag/models/escalation.py
──────────────────────────────
MongoDB document model for the `escalations` collection.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import Field

from app.models.base import MongoBaseModel, TimestampMixin


class EscalationState(str, Enum):
    OPEN       = "open"
    ASSIGNED   = "assigned"
    RESOLVED   = "resolved"
    CLOSED     = "closed"


class Escalation(MongoBaseModel, TimestampMixin):
    """Stored in `escalations` collection."""

    escalation_id:       str
    conversation_id:     str
    user_id:             Optional[str]    = None
    log_id:              Optional[str]    = None   # → retrieval_logs.log_id

    customer_question:   str
    ai_attempted_answer: Optional[str]   = None
    confidence_score:    Optional[float] = None
    reason:              str             = "low_confidence"

    state:               EscalationState = EscalationState.OPEN
    assigned_to:         Optional[str]   = None   # agent user_id
    resolution_note:     Optional[str]   = None
    resolved_at:         Optional[datetime] = None
