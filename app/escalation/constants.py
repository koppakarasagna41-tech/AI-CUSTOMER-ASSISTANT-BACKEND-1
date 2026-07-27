"""
app/escalation/constants.py
────────────────────────────
Escalation trigger types, states, and priority mappings.
"""

from __future__ import annotations


class EscalationTrigger:
    """All reasons an escalation can be created."""
    NEGATIVE_SENTIMENT    = "negative_sentiment"      # polarity ≤ threshold
    VERY_NEGATIVE         = "very_negative_sentiment" # very_negative label
    REPEATED_QUESTIONS    = "repeated_unanswered"     # N msgs no AI reply
    HUMAN_REQUEST         = "human_agent_requested"   # explicit keyword
    HIGH_PRIORITY         = "high_priority_ticket"    # ticket priority HIGH/CRITICAL
    MANUAL                = "manual"                  # admin-triggered

    @classmethod
    def all_values(cls) -> list[str]:
        return [
            cls.NEGATIVE_SENTIMENT, cls.VERY_NEGATIVE,
            cls.REPEATED_QUESTIONS, cls.HUMAN_REQUEST,
            cls.HIGH_PRIORITY, cls.MANUAL,
        ]


class EscalationState:
    OPEN        = "open"
    ASSIGNED    = "assigned"
    RESOLVED    = "resolved"
    CLOSED      = "closed"

    @classmethod
    def all_values(cls) -> list[str]:
        return [cls.OPEN, cls.ASSIGNED, cls.RESOLVED, cls.CLOSED]


class EscalationPriority:
    LOW      = "low"
    MEDIUM   = "medium"
    HIGH     = "high"
    CRITICAL = "critical"


# Trigger → default escalation priority
TRIGGER_PRIORITY: dict[str, str] = {
    EscalationTrigger.VERY_NEGATIVE:      EscalationPriority.CRITICAL,
    EscalationTrigger.HUMAN_REQUEST:      EscalationPriority.HIGH,
    EscalationTrigger.HIGH_PRIORITY:      EscalationPriority.HIGH,
    EscalationTrigger.NEGATIVE_SENTIMENT: EscalationPriority.MEDIUM,
    EscalationTrigger.REPEATED_QUESTIONS: EscalationPriority.MEDIUM,
    EscalationTrigger.MANUAL:             EscalationPriority.MEDIUM,
}

# Trigger → human-readable description
TRIGGER_DESCRIPTIONS: dict[str, str] = {
    EscalationTrigger.NEGATIVE_SENTIMENT:
        "Conversation sentiment is negative — customer appears frustrated.",
    EscalationTrigger.VERY_NEGATIVE:
        "Customer is very angry or using strong negative language.",
    EscalationTrigger.REPEATED_QUESTIONS:
        "Customer has sent multiple messages without receiving an AI response.",
    EscalationTrigger.HUMAN_REQUEST:
        "Customer explicitly requested to speak with a human agent.",
    EscalationTrigger.HIGH_PRIORITY:
        "A high-priority or critical support ticket was created for this conversation.",
    EscalationTrigger.MANUAL:
        "Escalation was triggered manually by an admin.",
}
