"""
app/models/conversation.py
───────────────────────────
MongoDB document model for the `conversations` collection.
"""

from enum import Enum
from typing import Optional

from pydantic import Field

from .base import MongoBaseModel, PyObjectId, TimestampMixin


class ConversationStatus(str, Enum):
    OPEN     = "open"
    PENDING  = "pending"
    RESOLVED = "resolved"
    CLOSED   = "closed"


class ConversationDocument(MongoBaseModel, TimestampMixin):
    """
    Represents a support conversation document in MongoDB.

    A conversation groups multiple messages between a user and the AI.
    `conversation_id` is a short human-readable identifier separate from
    the internal ObjectId.
    """

    conversation_id: str                             # e.g. "CONV-20260726-001"
    user_id:         Optional[str]  = None           # references users._id
    title:           Optional[str]  = None           # auto-generated or user-supplied
    status:          ConversationStatus = ConversationStatus.OPEN
    message_count:   int            = 0
    last_message_at: Optional[str]  = None           # ISO datetime string
    tags:            list[str]      = Field(default_factory=list)
    metadata:        dict           = Field(default_factory=dict)
