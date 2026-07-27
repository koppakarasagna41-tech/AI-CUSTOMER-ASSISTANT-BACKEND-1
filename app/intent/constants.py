"""
app/intent/constants.py
────────────────────────
All supported intent labels and their metadata.

INTENTS dict is the single source of truth — used by the classifier
prompt, the validator, and the response schemas.
"""

from __future__ import annotations

# ── Canonical intent labels ───────────────────────────────────

class Intent:
    GREETING        = "greeting"
    QUESTION        = "question"
    COMPLAINT       = "complaint"
    REFUND_REQUEST  = "refund_request"
    TECHNICAL_ISSUE = "technical_issue"
    BILLING         = "billing"
    FEEDBACK        = "feedback"
    GOODBYE         = "goodbye"
    UNKNOWN         = "unknown"

    @classmethod
    def all_values(cls) -> list[str]:
        return [
            cls.GREETING, cls.QUESTION, cls.COMPLAINT,
            cls.REFUND_REQUEST, cls.TECHNICAL_ISSUE,
            cls.BILLING, cls.FEEDBACK, cls.GOODBYE, cls.UNKNOWN,
        ]

    @classmethod
    def is_valid(cls, value: str) -> bool:
        return value in cls.all_values()


# ── Intent metadata ───────────────────────────────────────────
# Used in prompts and for prompt category mapping

INTENT_META: dict[str, dict] = {
    Intent.GREETING: {
        "label":       "Greeting",
        "description": "Customer is saying hello, starting a conversation, or making small talk.",
        "examples":    ["Hi there!", "Good morning", "Hello, I need help", "Hey"],
        "prompt_category": "greetings",
    },
    Intent.QUESTION: {
        "label":       "Question",
        "description": "Customer is asking for information, guidance, or how something works.",
        "examples":    ["How do I change my password?", "What are your business hours?"],
        "prompt_category": "customer_support",
    },
    Intent.COMPLAINT: {
        "label":       "Complaint",
        "description": "Customer is expressing dissatisfaction, frustration, or a negative experience.",
        "examples":    ["This is unacceptable", "I'm very disappointed", "Your service is terrible"],
        "prompt_category": "complaint",
    },
    Intent.REFUND_REQUEST: {
        "label":       "Refund Request",
        "description": "Customer explicitly wants a refund, return, or money back.",
        "examples":    ["I want my money back", "Please refund my order", "Cancel and refund"],
        "prompt_category": "refund",
    },
    Intent.TECHNICAL_ISSUE: {
        "label":       "Technical Issue",
        "description": "Customer reports a bug, error, crash, or something not working correctly.",
        "examples":    ["The app crashes", "I keep getting an error", "The page won't load"],
        "prompt_category": "technical",
    },
    Intent.BILLING: {
        "label":       "Billing",
        "description": "Customer has questions about charges, invoices, subscriptions, or payments.",
        "examples":    ["Why was I charged twice?", "My payment failed", "I need my invoice"],
        "prompt_category": "billing",
    },
    Intent.FEEDBACK: {
        "label":       "Feedback",
        "description": "Customer is sharing a suggestion, positive experience, or product opinion.",
        "examples":    ["I love the new feature", "You should add dark mode", "Great service!"],
        "prompt_category": "customer_support",
    },
    Intent.GOODBYE: {
        "label":       "Goodbye",
        "description": "Customer is ending the conversation.",
        "examples":    ["Thanks, bye!", "That's all I needed", "Goodbye", "See you"],
        "prompt_category": "greetings",
    },
    Intent.UNKNOWN: {
        "label":       "Unknown",
        "description": "The intent could not be determined with sufficient confidence.",
        "examples":    [],
        "prompt_category": "unknown",
    },
}
