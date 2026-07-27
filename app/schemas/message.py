"""app/schemas/message.py — Request/response schemas for messages."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.message import MessageRole, MessageStatus


class MessageCreate(BaseModel):
    conversation_id: str
    role:            MessageRole = MessageRole.USER
    content:         str         = Field(..., min_length=1, max_length=10_000)


class MessageOut(BaseModel):
    id:              str
    conversation_id: str
    role:            MessageRole
    content:         str
    status:          MessageStatus
    tokens_used:     Optional[int] = None
    model_used:      Optional[str] = None
    created_at:      Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
