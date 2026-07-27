# app/escalation/services package
from .detector         import detect_escalation_signals, DetectedSignal
from .ticket_generator import generate_escalation_ticket
from .escalation_store import (
    save_escalation_event, get_escalation_event,
    list_escalation_events, get_conversation_escalations,
    update_escalation_event, mark_admin_notified, escalation_summary,
)
from .notification import notify_admin

__all__ = [
    "detect_escalation_signals", "DetectedSignal",
    "generate_escalation_ticket",
    "save_escalation_event", "get_escalation_event",
    "list_escalation_events", "get_conversation_escalations",
    "update_escalation_event", "mark_admin_notified", "escalation_summary",
    "notify_admin",
]
