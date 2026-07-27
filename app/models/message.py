"""
app/models/message.py
──────────────────────
MongoDB document model for the `messages` collection.
"""

from enum import Enum
from typing import Optional

from pydantic import Field

from .base import MongoBaseModel, TimestampMixin


class MessageRole(str, Enum):
    USER      = "user"
    ASSISTANT = "assistant"
    SYSTEM    = "system"


class MessageStatus(str, Enum):
    SENT      = "sent"
    DELIVERED = "delivered"
    READ      = "read"
    FAILED    = "failed"


class MessageDocument(MongoBaseModel, TimestampMixin):
    """
    A single chat message belonging to a conversation.
    """

    conversation_id: str                              # references conversations.conversation_id
    role:            MessageRole
    content:         str
    status:          MessageStatus = MessageStatus.SENT
    tokens_used:     Optional[int] = None             # AI token count — populated later
    model_used:      Optional[str] = None             # e.g. "gemini-pro" — populated later
    metadata:        dict          = Field(default_factory=dict)
