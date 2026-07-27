"""
app/schemas/chat.py
────────────────────
Request/response schemas for the AI chat endpoint.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Body for POST /api/v1/chat/{conversation_id}"""
    message: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="The user's message to the AI assistant.",
        examples=["My order hasn't arrived yet. Can you help?"],
    )


class MessageOut(BaseModel):
    """A single message as returned in the chat response."""
    id:              str
    conversation_id: str
    role:            str                  # "user" | "assistant"
    content:         str
    tokens_used:     Optional[int]        = None
    model_used:      Optional[str]        = None
    is_fallback:     bool                 = False
    created_at:      Optional[datetime]   = None


class ChatResponse(BaseModel):
    """Full response returned from POST /api/v1/chat/{conversation_id}"""
    conversation_id:  str
    user_message:     MessageOut
    ai_response:      MessageOut
    tokens_used:      int
    model_used:       str
    is_fallback:      bool = False


class StartChatRequest(BaseModel):
    """Body for POST /api/v1/chat — creates a conversation and sends first message."""
    message: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        examples=["Hi, I need help with my account."],
    )
    title:   Optional[str] = Field(
        None,
        max_length=200,
        description="Optional conversation title. Auto-generated if omitted.",
    )
