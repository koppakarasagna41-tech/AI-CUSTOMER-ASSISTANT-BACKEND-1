"""
app/escalation/services/detector.py
──────────────────────────────────────
Escalation Detection Engine.

Evaluates a conversation against 5 trigger conditions in severity order:

  1. HUMAN_REQUEST      — customer typed a human-agent keyword
  2. VERY_NEGATIVE      — latest user message is very_negative sentiment
  3. NEGATIVE_SENTIMENT — sustained negative polarity streak
  4. REPEATED_QUESTIONS — N consecutive user messages without an AI reply
  5. HIGH_PRIORITY      — linked ticket has HIGH or CRITICAL priority
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorCollection
from pymongo import DESCENDING

from app.config                       import settings
from app.escalation.constants         import (
    EscalationTrigger, TRIGGER_PRIORITY, TRIGGER_DESCRIPTIONS,
)
from app.sentiment.services.analyzer  import analyze_sentiment
from app.sentiment.constants           import Sentiment

logger = logging.getLogger(__name__)


@dataclass
class DetectedSignal:
    trigger:     str
    priority:    str
    description: str
    evidence:    dict = field(default_factory=dict)


def _get_human_keywords() -> list[str]:
    return [k.strip().lower() for k in settings.ESCALATION_HUMAN_KEYWORDS.split(",") if k.strip()]


def _contains_human_request(text: str) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in _get_human_keywords())


def _count_unanswered_streak(messages: list[dict]) -> int:
    """Count consecutive user messages at the end with no assistant reply after them."""
    streak = 0
    for msg in reversed(messages):
        if msg.get("role") == "user":
            streak += 1
        else:
            break
    return streak


async def detect_escalation_signals(
    conversation_id: str,
    messages_col:    AsyncIOMotorCollection,
    tickets_col:     AsyncIOMotorCollection,
    window:          int = 6,
) -> list[DetectedSignal]:
    """
    Evaluate a conversation and return all triggered escalation signals.
    Returns empty list when no escalation is needed.
    """
    signals: list[DetectedSignal] = []

    # Fetch recent messages
    cursor = (
        messages_col
        .find({"conversation_id": conversation_id})
        .sort("created_at", DESCENDING)
        .limit(window)
    )
    recent = await cursor.to_list(length=window)
    recent.reverse()  # oldest → newest

    if not recent:
        return signals

    user_messages    = [m for m in recent if m.get("role") == "user"]
    if not user_messages:
        return signals

    latest_user_text = user_messages[-1].get("content", "")

    # ── TRIGGER 1: Human-agent keyword ───────────────────────
    if _contains_human_request(latest_user_text):
        matched = [kw for kw in _get_human_keywords() if kw in latest_user_text.lower()]
        signals.append(DetectedSignal(
            trigger=EscalationTrigger.HUMAN_REQUEST,
            priority=TRIGGER_PRIORITY[EscalationTrigger.HUMAN_REQUEST],
            description=TRIGGER_DESCRIPTIONS[EscalationTrigger.HUMAN_REQUEST],
            evidence={
                "trigger_message":  latest_user_text[:300],
                "keywords_matched": matched,
            },
        ))
        logger.info("Escalation HUMAN_REQUEST | conv=%s keywords=%s", conversation_id, matched)

    # ── TRIGGER 2 & 3: Sentiment analysis ────────────────────
    polarities: list[float] = []
    sentiments: list[str]   = []

    for msg in user_messages:
        content = msg.get("content", "").strip()
        if content:
            result = await analyze_sentiment(content)
            polarities.append(result.polarity_score)
            sentiments.append(result.sentiment)

    if polarities:
        avg_polarity  = sum(polarities) / len(polarities)
        latest_sent   = sentiments[-1] if sentiments else Sentiment.NEUTRAL
        latest_polar  = polarities[-1] if polarities else 0.0

        # TRIGGER 2: Very negative latest message
        if latest_sent == Sentiment.VERY_NEGATIVE:
            signals.append(DetectedSignal(
                trigger=EscalationTrigger.VERY_NEGATIVE,
                priority=TRIGGER_PRIORITY[EscalationTrigger.VERY_NEGATIVE],
                description=TRIGGER_DESCRIPTIONS[EscalationTrigger.VERY_NEGATIVE],
                evidence={
                    "sentiment":       latest_sent,
                    "polarity_score":  latest_polar,
                    "trigger_message": latest_user_text[:300],
                },
            ))
            logger.info("Escalation VERY_NEGATIVE | conv=%s polarity=%.2f", conversation_id, latest_polar)

        # TRIGGER 3: Sustained negative streak
        elif avg_polarity <= settings.ESCALATION_SENTIMENT_POLARITY:
            streak = 0
            for s in reversed(sentiments):
                if s in (Sentiment.NEGATIVE, Sentiment.VERY_NEGATIVE):
                    streak += 1
                else:
                    break

            if streak >= settings.ESCALATION_NEGATIVE_STREAK:
                signals.append(DetectedSignal(
                    trigger=EscalationTrigger.NEGATIVE_SENTIMENT,
                    priority=TRIGGER_PRIORITY[EscalationTrigger.NEGATIVE_SENTIMENT],
                    description=TRIGGER_DESCRIPTIONS[EscalationTrigger.NEGATIVE_SENTIMENT],
                    evidence={
                        "average_polarity": round(avg_polarity, 3),
                        "negative_streak":  streak,
                        "sentiments":       sentiments,
                        "threshold":        settings.ESCALATION_SENTIMENT_POLARITY,
                    },
                ))
                logger.info(
                    "Escalation NEGATIVE_SENTIMENT | conv=%s streak=%d avg=%.2f",
                    conversation_id, streak, avg_polarity,
                )

    # ── TRIGGER 4: Repeated unanswered messages ───────────────
    unanswered = _count_unanswered_streak(recent)
    if unanswered >= settings.ESCALATION_UNANSWERED_THRESHOLD:
        signals.append(DetectedSignal(
            trigger=EscalationTrigger.REPEATED_QUESTIONS,
            priority=TRIGGER_PRIORITY[EscalationTrigger.REPEATED_QUESTIONS],
            description=TRIGGER_DESCRIPTIONS[EscalationTrigger.REPEATED_QUESTIONS],
            evidence={
                "unanswered_count": unanswered,
                "threshold":        settings.ESCALATION_UNANSWERED_THRESHOLD,
                "last_message":     latest_user_text[:300],
            },
        ))
        logger.info("Escalation REPEATED_QUESTIONS | conv=%s count=%d", conversation_id, unanswered)

    # ── TRIGGER 5: High/critical priority ticket ─────────────
    ticket = await tickets_col.find_one(
        {"conversation_id": conversation_id, "priority": {"$in": ["high", "critical"]}}
    )
    if ticket:
        signals.append(DetectedSignal(
            trigger=EscalationTrigger.HIGH_PRIORITY,
            priority=TRIGGER_PRIORITY[EscalationTrigger.HIGH_PRIORITY],
            description=TRIGGER_DESCRIPTIONS[EscalationTrigger.HIGH_PRIORITY],
            evidence={
                "ticket_id":       ticket.get("ticket_id", ""),
                "ticket_priority": ticket.get("priority", ""),
                "ticket_subject":  ticket.get("subject", "")[:200],
            },
        ))
        logger.info("Escalation HIGH_PRIORITY | conv=%s ticket=%s", conversation_id, ticket.get("ticket_id"))

    return signals
