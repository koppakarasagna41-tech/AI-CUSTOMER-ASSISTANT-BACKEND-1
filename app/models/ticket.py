"""
app/models/ticket.py
─────────────────────
MongoDB document model for the `tickets` collection.
"""

from enum import Enum
from typing import Optional
from pydantic import Field
from .base import MongoBaseModel, TimestampMixin


class TicketCategory(str, Enum):
    """
    7 supported ticket categories — auto-classified by Gemini
    or manually set at creation time.
    """
    TECHNICAL        = "technical"
    BILLING          = "billing"
    REFUND           = "refund"
    ACCOUNT          = "account"
    GENERAL_INQUIRY  = "general_inquiry"
    COMPLAINT        = "complaint"
    FEATURE_REQUEST  = "feature_request"


class TicketPriority(str, Enum):
    LOW      = "low"
    MEDIUM   = "medium"
    HIGH     = "high"
    CRITICAL = "critical"


class TicketStatus(str, Enum):
    OPEN        = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED    = "resolved"
    CLOSED      = "closed"


class TicketDocument(MongoBaseModel, TimestampMixin):
    """
    A support ticket — created manually or auto-generated from
    an escalated conversation.  Category and priority are
    auto-assigned by the Gemini classifier.
    """
    ticket_id:        str                                   # TKT-YYYYMMDD-XXXXXXXX (unique)
    user_id:          Optional[str]         = None
    conversation_id:  Optional[str]         = None
    subject:          str
    description:      Optional[str]         = None
    category:         TicketCategory        = TicketCategory.GENERAL_INQUIRY
    status:           TicketStatus          = TicketStatus.OPEN
    priority:         TicketPriority        = TicketPriority.MEDIUM
    assigned_to:      Optional[str]         = None
    resolved_at:      Optional[str]         = None

    # Classification metadata
    category_confidence:  float             = 0.0
    auto_classified:      bool              = True      # False when manually set
    classification_model: Optional[str]     = None

    tags:             list[str]             = Field(default_factory=list)
    metadata:         dict                  = Field(default_factory=dict)
