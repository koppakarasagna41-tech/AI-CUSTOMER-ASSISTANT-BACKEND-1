"""
app/escalation/services/notification.py
──────────────────────────────────────────
Admin notification service for escalation events.

Currently delivers in-app API notifications (stored in MongoDB).
The notify_admin() function is the integration point for future channels:
  - Email (SMTP)
  - Slack webhook
  - PagerDuty
  - Push notifications

Plug in any channel by adding a handler in _send_external_notification().
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorCollection

from app.escalation.services.escalation_store import (
    get_escalation_event, mark_admin_notified,
)
from app.utils.helpers import utc_now

logger = logging.getLogger(__name__)


async def notify_admin(
    col:           AsyncIOMotorCollection,
    escalation_id: str,
) -> dict:
    """
    Notify admins about an escalation event.

    Currently marks the event as notified in MongoDB (in-app notification).
    Add email/Slack/webhook integrations in _send_external_notification().

    Returns the notification payload.
    """
    event = await get_escalation_event(col, escalation_id)
    if not event:
        raise ValueError(f"Escalation '{escalation_id}' not found.")

    now = utc_now()

    payload = {
        "escalation_id":   escalation_id,
        "conversation_id": event["conversation_id"],
        "trigger":         event["trigger"],
        "priority":        event["priority"],
        "description":     event["description"],
        "evidence":        event.get("evidence", {}),
        "ticket_id":       event.get("ticket_id"),
        "user_id":         event.get("user_id"),
        "notified_at":     now.isoformat(),
    }

    # ── In-app: mark notified ────────────────────────────────
    await mark_admin_notified(col, escalation_id)

    # ── External channels (plug in here) ─────────────────────
    await _send_external_notification(payload)

    logger.info(
        "Admin notified | escalation=%s conv=%s trigger=%s priority=%s",
        escalation_id,
        event["conversation_id"],
        event["trigger"],
        event["priority"],
    )
    return payload


async def _send_external_notification(payload: dict) -> None:
    """
    Hook for external notification channels.
    Currently logs only — replace with real integrations when ready.

    To add Slack:
        async with aiohttp.ClientSession() as s:
            await s.post(SLACK_WEBHOOK_URL, json={"text": build_slack_message(payload)})

    To add Email:
        await send_email(to=ADMIN_EMAIL, subject=..., body=...)
    """
    logger.info(
        "[NOTIFY] Escalation alert | id=%s trigger=%s priority=%s conv=%s",
        payload["escalation_id"],
        payload["trigger"],
        payload["priority"],
        payload["conversation_id"],
    )
