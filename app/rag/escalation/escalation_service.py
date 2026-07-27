"""
app/rag/escalation/escalation_service.py
──────────────────────────────────────────
Creates escalation records when RAG confidence is too low.

An escalation record captures:
  - The original question
  - What the AI attempted (if anything)
  - The confidence score that triggered escalation
  - Links back to the retrieval log

In a production system this would also notify an agent queue.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorCollection

from app.utils.helpers import utc_now

logger = logging.getLogger(__name__)


def _gen_escalation_id() -> str:
    date = datetime.now(tz=timezone.utc).strftime("%Y%m%d")
    uid  = uuid.uuid4().hex[:8].upper()
    return f"ESC-{date}-{uid}"


async def create_escalation(
    col:                 AsyncIOMotorCollection,
    conversation_id:     str,
    customer_question:   str,
    confidence_score:    float,
    ai_attempted_answer: Optional[str] = None,
    user_id:             Optional[str] = None,
    log_id:              Optional[str] = None,
    reason:              str           = "low_confidence",
) -> str:
    """
    Persist an escalation record and return its escalation_id.
    """
    esc_id = _gen_escalation_id()
    now    = utc_now()

    doc = {
        "escalation_id":       esc_id,
        "conversation_id":     conversation_id,
        "user_id":             user_id,
        "log_id":              log_id,
        "customer_question":   customer_question,
        "ai_attempted_answer": ai_attempted_answer,
        "confidence_score":    confidence_score,
        "reason":              reason,
        "state":               "open",
        "assigned_to":         None,
        "resolution_note":     None,
        "resolved_at":         None,
        "created_at":          now,
        "updated_at":          now,
    }

    await col.insert_one(doc)
    logger.info(
        "Escalation created",
        extra={
            "component": "app",
            "event": "escalation_created",
            "escalation_id": esc_id,
            "conversation_id": conversation_id,
            "user_id": user_id,
            "confidence_score": confidence_score,
            "reason": reason,
        },
    )
    return esc_id
