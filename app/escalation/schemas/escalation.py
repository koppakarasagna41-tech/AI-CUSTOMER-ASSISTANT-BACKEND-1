"""app/escalation/schemas/escalation.py — Request/response schemas."""

from __future__ import annotations
from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field, ConfigDict


# ── Requests ──────────────────────────────────────────────────

class EscalationCheckRequest(BaseModel):
    """POST /escalation/check — analyse a conversation for escalation signals."""
    conversation_id: str = Field(..., description="Conversation to evaluate")


class ManualEscalationRequest(BaseModel):
    """POST /escalation/manual — admin manually triggers an escalation."""
    conversation_id: str
    reason:          str  = Field(..., min_length=5, max_length=500)


class ResolveEscalationRequest(BaseModel):
    """PATCH /escalation/{id}/resolve — resolve an escalation."""
    resolution_note: str  = Field(..., min_length=5, max_length=1000)
    assigned_to:     Optional[str] = None


class AssignEscalationRequest(BaseModel):
    """PATCH /escalation/{id}/assign"""
    assigned_to: str = Field(..., description="User ID of the agent to assign")


# ── Responses ─────────────────────────────────────────────────

class EscalationSignal(BaseModel):
    """A single detected escalation signal before a decision is made."""
    trigger:     str
    priority:    str
    description: str
    evidence:    dict[str, Any] = {}


class EscalationCheckResult(BaseModel):
    """Returned from POST /escalation/check."""
    conversation_id:  str
    should_escalate:  bool
    signals:          list[EscalationSignal]     # all triggers found
    primary_trigger:  Optional[str]              # highest-priority trigger
    priority:         Optional[str]
    escalation_id:    Optional[str]  = None      # set if escalation was created
    ticket_id:        Optional[str]  = None      # set if ticket was generated
    message:          str


class EscalationEventOut(BaseModel):
    """Full escalation event record returned from the API."""
    id:              str
    escalation_id:   str
    conversation_id: str
    user_id:         Optional[str]      = None
    ticket_id:       Optional[str]      = None
    trigger:         str
    priority:        str
    description:     str
    state:           str
    evidence:        dict[str, Any]     = {}
    assigned_to:     Optional[str]      = None
    resolved_at:     Optional[datetime] = None
    resolution_note: Optional[str]      = None
    admin_notified:  bool               = False
    notified_at:     Optional[datetime] = None
    created_at:      Optional[datetime] = None
    updated_at:      Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class AdminNotificationOut(BaseModel):
    """Returned from POST /escalation/{id}/notify."""
    escalation_id:  str
    conversation_id: str
    trigger:        str
    priority:       str
    description:    str
    notified_at:    datetime
    message:        str
