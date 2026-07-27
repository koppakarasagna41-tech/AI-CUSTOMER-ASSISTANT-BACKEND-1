"""app/schemas/ticket.py — Request/response schemas for tickets."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field
from app.models.ticket import TicketCategory, TicketPriority, TicketStatus


class TicketCreate(BaseModel):
    """
    Create a new ticket.
    If `category` is omitted the system auto-classifies using Gemini.
    If `priority` is omitted the system auto-assigns based on category + keywords.
    """
    subject:         str             = Field(..., min_length=3, max_length=200)
    description:     Optional[str]  = Field(None, max_length=5000)
    user_id:         Optional[str]  = None
    conversation_id: Optional[str]  = None
    # Leave None to trigger auto-classification
    category:        Optional[TicketCategory] = None
    priority:        Optional[TicketPriority] = None
    tags:            list[str]      = Field(default_factory=list)


class TicketUpdate(BaseModel):
    subject:     Optional[str]           = Field(None, max_length=200)
    description: Optional[str]           = Field(None, max_length=5000)
    status:      Optional[TicketStatus]  = None
    priority:    Optional[TicketPriority] = None
    category:    Optional[TicketCategory] = None
    assigned_to: Optional[str]           = None
    tags:        Optional[list[str]]     = None


class ClassificationDetail(BaseModel):
    """Embedded in TicketOut to show how the ticket was classified."""
    category:    str
    confidence:  float
    auto:        bool
    model_used:  Optional[str] = None


class TicketOut(BaseModel):
    id:               str
    ticket_id:        str
    user_id:          Optional[str]             = None
    conversation_id:  Optional[str]             = None
    subject:          str
    description:      Optional[str]             = None
    category:         TicketCategory
    status:           TicketStatus
    priority:         TicketPriority
    assigned_to:      Optional[str]             = None
    resolved_at:      Optional[str]             = None
    classification:   Optional[ClassificationDetail] = None
    tags:             list[str]                 = []
    created_at:       Optional[datetime]        = None
    updated_at:       Optional[datetime]        = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class TicketClassifyRequest(BaseModel):
    """Re-classify an existing ticket by ticket_id."""
    ticket_id: str


class TicketStatsOut(BaseModel):
    """Summary stats returned from GET /tickets/stats."""
    total:           int
    by_status:       dict[str, int]
    by_category:     dict[str, int]
    by_priority:     dict[str, int]
