"""
app/models/analytics.py
────────────────────────
MongoDB document model for the `analytics` collection.

Analytics documents are raw event records.  A background job (not yet
implemented) aggregates them into summary statistics.

The collection has a TTL index of 90 days — old raw events are
automatically purged by MongoDB Atlas.
"""

from enum import Enum
from typing import Any, Optional

from pydantic import Field

from .base import MongoBaseModel, TimestampMixin


class AnalyticsEventType(str, Enum):
    CONVERSATION_STARTED  = "conversation_started"
    CONVERSATION_RESOLVED = "conversation_resolved"
    MESSAGE_SENT          = "message_sent"
    TICKET_CREATED        = "ticket_created"
    TICKET_RESOLVED       = "ticket_resolved"
    USER_REGISTERED       = "user_registered"
    AI_RESPONSE           = "ai_response"
    ERROR                 = "error"


class AnalyticsDocument(MongoBaseModel, TimestampMixin):
    """
    A single analytics event record.
    """

    event_type:  AnalyticsEventType
    user_id:     Optional[str]      = None   # actor (if known)
    entity_id:   Optional[str]      = None   # e.g. conversation_id, ticket_id
    entity_type: Optional[str]      = None   # e.g. "conversation", "ticket"
    value:       Optional[float]    = None   # numeric metric (tokens, latency ms, etc.)
    properties:  dict[str, Any]     = Field(default_factory=dict)  # arbitrary extra data
