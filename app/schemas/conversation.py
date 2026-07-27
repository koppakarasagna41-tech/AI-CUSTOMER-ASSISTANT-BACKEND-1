"""app/schemas/conversation.py — Request/response schemas for conversations."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.conversation import ConversationStatus


class ConversationCreate(BaseModel):
    title:   Optional[str]      = Field(None, max_length=200)
    user_id: Optional[str]      = None
    tags:    list[str]          = Field(default_factory=list)


class ConversationUpdate(BaseModel):
    title:  Optional[str]               = Field(None, max_length=200)
    status: Optional[ConversationStatus] = None
    tags:   Optional[list[str]]          = None


class ConversationOut(BaseModel):
    id:              str
    conversation_id: str
    user_id:         Optional[str]             = None
    title:           Optional[str]             = None
    status:          ConversationStatus
    message_count:   int                       = 0
    last_message_at: Optional[str]             = None
    tags:            list[str]                 = []

    # Sentiment fields — populated by POST /sentiment/conversation/{id}
    sentiment:             Optional[str]   = None   # dominant sentiment label
    sentiment_polarity:    Optional[float] = None   # average polarity score
    sentiment_trend:       Optional[str]   = None   # improving | declining | stable
    sentiment_updated_at:  Optional[str]   = None

    created_at:      Optional[datetime]        = None
    updated_at:      Optional[datetime]        = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
