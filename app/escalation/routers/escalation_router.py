"""
app/escalation/routers/escalation_router.py
────────────────────────────────────────────
Escalation Detection & Management API.

POST /escalation/check/{conversation_id}
    Evaluate a conversation for all 5 escalation triggers.
    Automatically creates an escalation event + ticket if triggered.
    Notifies admin immediately for CRITICAL/HIGH priority.

POST /escalation/manual
    Admin manually escalates a conversation.

GET  /escalation
    Paginated list with filters (state, trigger, priority).

GET  /escalation/summary
    Aggregated counts by state, trigger, and priority.

GET  /escalation/conversation/{conversation_id}
    All escalation events for a specific conversation.

GET  /escalation/{escalation_id}
    Single escalation event detail.

PATCH /escalation/{escalation_id}/assign
    Assign escalation to a human agent.

PATCH /escalation/{escalation_id}/resolve
    Mark escalation as resolved with a note.

POST  /escalation/{escalation_id}/notify
    Re-send admin notification for an escalation.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from motor.motor_asyncio import AsyncIOMotorCollection

from app.core.auth_deps  import get_current_user, require_admin
from app.core.exceptions import BadRequestError, NotFoundError
from app.core.responses  import success_response, paginated_response
from app.database        import (
    ConversationsCollection,
    MessagesCollection,
    TicketsCollection,
    EscalationEventsCollection,
)
from app.escalation.constants import EscalationTrigger, EscalationState, TRIGGER_DESCRIPTIONS
from app.escalation.schemas   import (
    EscalationCheckResult, EscalationSignal,
    EscalationEventOut, AdminNotificationOut,
    ManualEscalationRequest,
    ResolveEscalationRequest, AssignEscalationRequest,
)
from app.escalation.services  import (
    detect_escalation_signals, DetectedSignal,
    generate_escalation_ticket,
    save_escalation_event, get_escalation_event,
    list_escalation_events, get_conversation_escalations,
    update_escalation_event, escalation_summary,
    notify_admin,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/escalation", tags=["Escalation Detection"])


# ── Helper ────────────────────────────────────────────────────

def _to_event_out(doc: dict) -> dict:
    return EscalationEventOut(**{**doc, "id": doc["_id"]}).model_dump()


def _signal_to_schema(s: DetectedSignal) -> EscalationSignal:
    return EscalationSignal(
        trigger=s.trigger,
        priority=s.priority,
        description=s.description,
        evidence=s.evidence,
    )


def _top_priority(signals: list[DetectedSignal]) -> tuple[str, str]:
    """Return (trigger, priority) of the highest-severity signal."""
    order = ["critical", "high", "medium", "low"]
    for lvl in order:
        for s in signals:
            if s.priority == lvl:
                return s.trigger, s.priority
    return signals[0].trigger, signals[0].priority


# ── POST /escalation/check/{conversation_id} ─────────────────

@router.post(
    "/check/{conversation_id}",
    summary="Evaluate conversation for escalation triggers",
)
async def check_escalation(
    conversation_id: str,
    current_user:    dict                   = Depends(get_current_user),
    conv_col:        AsyncIOMotorCollection = Depends(ConversationsCollection),
    msg_col:         AsyncIOMotorCollection = Depends(MessagesCollection),
    tickets_col:     AsyncIOMotorCollection = Depends(TicketsCollection),
    esc_col:         AsyncIOMotorCollection = Depends(EscalationEventsCollection),
):
    """
    Runs all 5 escalation detectors against the conversation.
    If any trigger fires:
      1. Creates an escalation event in MongoDB
      2. Auto-generates an escalation support ticket
      3. Notifies admin if priority is HIGH or CRITICAL
    """
    # Verify conversation exists
    conv = await conv_col.find_one({"conversation_id": conversation_id})
    if not conv:
        raise NotFoundError(f"Conversation '{conversation_id}' not found.", error_code="CONV_NOT_FOUND")

    user_id = current_user.get("_id")

    # Run all detectors
    signals = await detect_escalation_signals(
        conversation_id=conversation_id,
        messages_col=msg_col,
        tickets_col=tickets_col,
    )

    if not signals:
        return success_response(
            data=EscalationCheckResult(
                conversation_id=conversation_id,
                should_escalate=False,
                signals=[],
                primary_trigger=None,
                priority=None,
                message="No escalation triggers detected.",
            ).model_dump(),
            message="No escalation required.",
        )

    # Use highest-priority signal as primary
    primary_trigger, primary_priority = _top_priority(signals)
    primary_signal  = next(s for s in signals if s.trigger == primary_trigger)

    # Generate escalation ticket
    ticket = await generate_escalation_ticket(
        tickets_col=tickets_col,
        conversation_id=conversation_id,
        trigger=primary_trigger,
        description=primary_signal.description,
        user_id=user_id,
        evidence=primary_signal.evidence,
    )
    ticket_id = ticket.get("ticket_id") if ticket else None

    # Save escalation event
    escalation_id = await save_escalation_event(
        col=esc_col,
        conversation_id=conversation_id,
        signal=primary_signal,
        user_id=user_id,
        ticket_id=ticket_id,
    )

    # Auto-notify admin for high/critical
    if primary_priority in ("high", "critical"):
        await notify_admin(col=esc_col, escalation_id=escalation_id)

    logger.info(
        "Escalation created | id=%s conv=%s trigger=%s priority=%s ticket=%s",
        escalation_id, conversation_id, primary_trigger, primary_priority, ticket_id,
    )

    result = EscalationCheckResult(
        conversation_id=conversation_id,
        should_escalate=True,
        signals=[_signal_to_schema(s) for s in signals],
        primary_trigger=primary_trigger,
        priority=primary_priority,
        escalation_id=escalation_id,
        ticket_id=ticket_id,
        message=(
            f"Escalated: {primary_signal.description} "
            f"[{primary_priority.upper()}]"
        ),
    )

    return success_response(
        data=result.model_dump(),
        message=f"Conversation escalated ({primary_priority.upper()}) — ticket {ticket_id} created.",
    )


# ── POST /escalation/manual ───────────────────────────────────

@router.post(
    "/manual",
    status_code=201,
    summary="Manually escalate a conversation [admin]",
)
async def manual_escalate(
    payload:     ManualEscalationRequest,
    admin:       dict                   = Depends(require_admin),
    conv_col:    AsyncIOMotorCollection = Depends(ConversationsCollection),
    tickets_col: AsyncIOMotorCollection = Depends(TicketsCollection),
    esc_col:     AsyncIOMotorCollection = Depends(EscalationEventsCollection),
):
    conv = await conv_col.find_one({"conversation_id": payload.conversation_id})
    if not conv:
        raise NotFoundError(f"Conversation '{payload.conversation_id}' not found.", error_code="CONV_NOT_FOUND")

    from app.escalation.constants import TRIGGER_PRIORITY
    signal = DetectedSignal(
        trigger=EscalationTrigger.MANUAL,
        priority=TRIGGER_PRIORITY[EscalationTrigger.MANUAL],
        description=payload.reason,
        evidence={"admin_id": admin.get("_id"), "reason": payload.reason},
    )

    ticket = await generate_escalation_ticket(
        tickets_col=tickets_col,
        conversation_id=payload.conversation_id,
        trigger=EscalationTrigger.MANUAL,
        description=payload.reason,
        user_id=conv.get("user_id"),
        evidence=signal.evidence,
    )
    ticket_id     = ticket.get("ticket_id") if ticket else None
    escalation_id = await save_escalation_event(
        col=esc_col,
        conversation_id=payload.conversation_id,
        signal=signal,
        user_id=conv.get("user_id"),
        ticket_id=ticket_id,
    )
    await notify_admin(col=esc_col, escalation_id=escalation_id)

    return success_response(
        data={"escalation_id": escalation_id, "ticket_id": ticket_id},
        message=f"Manual escalation created — ticket {ticket_id}.",
    )


# ── GET /escalation ───────────────────────────────────────────

@router.get("", summary="List escalation events")
async def list_escalations(
    page:            int           = Query(1,  ge=1),
    page_size:       int           = Query(20, ge=1, le=100),
    state:           Optional[str] = Query(None),
    trigger:         Optional[str] = Query(None),
    priority:        Optional[str] = Query(None),
    conversation_id: Optional[str] = Query(None),
    current_user:    dict                   = Depends(get_current_user),
    esc_col:         AsyncIOMotorCollection = Depends(EscalationEventsCollection),
):
    role    = current_user.get("role", "customer")
    user_id = current_user.get("_id") if role != "admin" else None

    skip        = (page - 1) * page_size
    docs, total = await list_escalation_events(
        col=esc_col, skip=skip, limit=page_size,
        state=state, trigger=trigger, priority=priority,
        conversation_id=conversation_id, user_id=user_id,
    )
    return paginated_response(
        data=[_to_event_out(d) for d in docs],
        total_items=total, page=page, page_size=page_size,
        message="Escalation events retrieved.",
    )


# ── GET /escalation/summary ───────────────────────────────────

@router.get("/summary", summary="Aggregated escalation counts [admin]")
async def get_summary(
    _:       dict                   = Depends(require_admin),
    esc_col: AsyncIOMotorCollection = Depends(EscalationEventsCollection),
):
    data = await escalation_summary(esc_col)
    return success_response(data=data, message="Escalation summary retrieved.")


# ── GET /escalation/conversation/{conversation_id} ────────────

@router.get(
    "/conversation/{conversation_id}",
    summary="Get all escalations for a conversation",
)
async def get_conv_escalations(
    conversation_id: str,
    current_user:    dict                   = Depends(get_current_user),
    esc_col:         AsyncIOMotorCollection = Depends(EscalationEventsCollection),
):
    docs  = await get_conversation_escalations(esc_col, conversation_id)
    return success_response(
        data=[_to_event_out(d) for d in docs],
        message=f"{len(docs)} escalation(s) found.",
    )


# ── GET /escalation/{escalation_id} ──────────────────────────

@router.get("/{escalation_id}", summary="Get escalation event by ID")
async def get_escalation(
    escalation_id: str,
    current_user:  dict                   = Depends(get_current_user),
    esc_col:       AsyncIOMotorCollection = Depends(EscalationEventsCollection),
):
    doc = await get_escalation_event(esc_col, escalation_id)
    if not doc:
        raise NotFoundError(f"Escalation '{escalation_id}' not found.", error_code="ESC_NOT_FOUND")
    return success_response(data=_to_event_out(doc), message="Escalation retrieved.")


# ── PATCH /escalation/{id}/assign ────────────────────────────

@router.patch("/{escalation_id}/assign", summary="Assign escalation to agent [admin]")
async def assign_escalation(
    escalation_id: str,
    payload:       AssignEscalationRequest,
    _:             dict                   = Depends(require_admin),
    esc_col:       AsyncIOMotorCollection = Depends(EscalationEventsCollection),
):
    doc = await get_escalation_event(esc_col, escalation_id)
    if not doc:
        raise NotFoundError(f"Escalation '{escalation_id}' not found.", error_code="ESC_NOT_FOUND")

    await update_escalation_event(esc_col, escalation_id, {
        "assigned_to": payload.assigned_to,
        "state":       EscalationState.ASSIGNED,
    })
    updated = await get_escalation_event(esc_col, escalation_id)
    return success_response(data=_to_event_out(updated), message="Escalation assigned.")


# ── PATCH /escalation/{id}/resolve ───────────────────────────

@router.patch("/{escalation_id}/resolve", summary="Resolve an escalation [admin]")
async def resolve_escalation(
    escalation_id: str,
    payload:       ResolveEscalationRequest,
    _:             dict                   = Depends(require_admin),
    esc_col:       AsyncIOMotorCollection = Depends(EscalationEventsCollection),
):
    doc = await get_escalation_event(esc_col, escalation_id)
    if not doc:
        raise NotFoundError(f"Escalation '{escalation_id}' not found.", error_code="ESC_NOT_FOUND")

    from app.utils.helpers import utc_now
    patch = {
        "state":           EscalationState.RESOLVED,
        "resolution_note": payload.resolution_note,
        "resolved_at":     utc_now(),
    }
    if payload.assigned_to:
        patch["assigned_to"] = payload.assigned_to

    await update_escalation_event(esc_col, escalation_id, patch)
    updated = await get_escalation_event(esc_col, escalation_id)
    return success_response(data=_to_event_out(updated), message="Escalation resolved.")


# ── POST /escalation/{id}/notify ─────────────────────────────

@router.post(
    "/{escalation_id}/notify",
    summary="Re-send admin notification for an escalation [admin]",
)
async def send_notification(
    escalation_id: str,
    _:             dict                   = Depends(require_admin),
    esc_col:       AsyncIOMotorCollection = Depends(EscalationEventsCollection),
):
    doc = await get_escalation_event(esc_col, escalation_id)
    if not doc:
        raise NotFoundError(f"Escalation '{escalation_id}' not found.", error_code="ESC_NOT_FOUND")

    payload = await notify_admin(col=esc_col, escalation_id=escalation_id)

    return success_response(
        data=AdminNotificationOut(
            escalation_id=escalation_id,
            conversation_id=payload["conversation_id"],
            trigger=payload["trigger"],
            priority=payload["priority"],
            description=payload["description"],
            notified_at=payload["notified_at"],
            message="Admin notified successfully.",
        ).model_dump(),
        message="Notification sent.",
    )
