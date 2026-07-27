"""
app/escalation/services/ticket_generator.py
─────────────────────────────────────────────
Auto-generates a support ticket when a conversation is escalated.
Maps escalation trigger → ticket category and priority.
"""

import logging
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorCollection

from app.escalation.constants  import EscalationTrigger
from app.models.ticket         import TicketCategory, TicketPriority
from app.services.ticket_service import create_ticket

logger = logging.getLogger(__name__)

# Trigger → ticket category
TRIGGER_TO_CATEGORY: dict[str, TicketCategory] = {
    EscalationTrigger.HUMAN_REQUEST:      TicketCategory.GENERAL_INQUIRY,
    EscalationTrigger.VERY_NEGATIVE:      TicketCategory.COMPLAINT,
    EscalationTrigger.NEGATIVE_SENTIMENT: TicketCategory.COMPLAINT,
    EscalationTrigger.REPEATED_QUESTIONS: TicketCategory.GENERAL_INQUIRY,
    EscalationTrigger.HIGH_PRIORITY:      TicketCategory.COMPLAINT,
    EscalationTrigger.MANUAL:             TicketCategory.GENERAL_INQUIRY,
}

# Trigger → ticket priority
TRIGGER_TO_PRIORITY: dict[str, TicketPriority] = {
    EscalationTrigger.VERY_NEGATIVE:      TicketPriority.CRITICAL,
    EscalationTrigger.HUMAN_REQUEST:      TicketPriority.HIGH,
    EscalationTrigger.HIGH_PRIORITY:      TicketPriority.HIGH,
    EscalationTrigger.NEGATIVE_SENTIMENT: TicketPriority.MEDIUM,
    EscalationTrigger.REPEATED_QUESTIONS: TicketPriority.MEDIUM,
    EscalationTrigger.MANUAL:             TicketPriority.MEDIUM,
}


async def generate_escalation_ticket(
    tickets_col:     AsyncIOMotorCollection,
    conversation_id: str,
    trigger:         str,
    description:     str,
    user_id:         Optional[str] = None,
    evidence:        dict          = None,
) -> Optional[dict]:
    """
    Create a support ticket for an escalated conversation.
    Returns the created ticket document, or None on failure.
    """
    try:
        category = TRIGGER_TO_CATEGORY.get(trigger, TicketCategory.COMPLAINT)
        priority = TRIGGER_TO_PRIORITY.get(trigger, TicketPriority.MEDIUM)

        subject     = f"[ESCALATION] Conversation {conversation_id}"
        desc_parts  = [f"Escalation reason: {description}"]
        if evidence:
            for k, v in list(evidence.items())[:5]:
                desc_parts.append(f"{k}: {v}")
        full_desc = "\n".join(desc_parts)

        ticket = await create_ticket(
            col=tickets_col,
            subject=subject,
            description=full_desc,
            user_id=user_id,
            conversation_id=conversation_id,
            category=category,
            priority=priority,
            tags=["escalation", trigger.replace("_", "-")],
        )

        logger.info(
            "Escalation ticket created | ticket=%s conv=%s trigger=%s priority=%s",
            ticket.get("ticket_id"), conversation_id, trigger, priority.value,
        )
        return ticket

    except Exception as exc:
        logger.error("Failed to generate escalation ticket: %s", exc)
        return None
