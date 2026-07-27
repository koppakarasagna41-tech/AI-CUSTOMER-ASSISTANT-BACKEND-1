"""
app/sentiment/constants.py
───────────────────────────
Supported sentiment labels, scores, and thresholds.

Polarity scale (used internally for aggregation):
  positive      →  1.0
  neutral       →  0.0
  negative      → -1.0
  very_negative → -2.0
"""

from __future__ import annotations


class Sentiment:
    POSITIVE      = "positive"
    NEUTRAL       = "neutral"
    NEGATIVE      = "negative"
    VERY_NEGATIVE = "very_negative"

    @classmethod
    def all_values(cls) -> list[str]:
        return [cls.POSITIVE, cls.NEUTRAL, cls.NEGATIVE, cls.VERY_NEGATIVE]

    @classmethod
    def is_valid(cls, value: str) -> bool:
        return value in cls.all_values()


SENTIMENT_META: dict[str, dict] = {
    Sentiment.POSITIVE: {
        "label":       "Positive",
        "description": "Customer is satisfied, happy, grateful, or expressing approval.",
        "examples":    ["Thank you so much!", "Great service!", "This is perfect"],
        "polarity":    1.0,
        "emoji":       "😊",
    },
    Sentiment.NEUTRAL: {
        "label":       "Neutral",
        "description": "Customer is asking a question or stating a fact without emotion.",
        "examples":    ["How do I reset my password?", "I need my invoice"],
        "polarity":    0.0,
        "emoji":       "😐",
    },
    Sentiment.NEGATIVE: {
        "label":       "Negative",
        "description": "Customer is frustrated, unhappy, or dissatisfied.",
        "examples":    ["This is not working", "I'm disappointed", "Still not fixed"],
        "polarity":    -1.0,
        "emoji":       "😞",
    },
    Sentiment.VERY_NEGATIVE: {
        "label":       "Very Negative",
        "description": "Customer is very angry, threatening to leave, or using strong negative language.",
        "examples":    ["This is absolutely unacceptable!", "I want to cancel everything", "Terrible experience!"],
        "polarity":    -2.0,
        "emoji":       "😡",
    },
}

# Polarity score → sentiment label (for aggregation)
POLARITY_THRESHOLDS = [
    (0.5,   Sentiment.POSITIVE),
    (-0.5,  Sentiment.NEUTRAL),
    (-1.5,  Sentiment.NEGATIVE),
    (-999,  Sentiment.VERY_NEGATIVE),
]


def polarity_to_sentiment(score: float) -> str:
    """Convert a numeric polarity score back to a sentiment label."""
    for threshold, label in POLARITY_THRESHOLDS:
        if score >= threshold:
            return label
    return Sentiment.VERY_NEGATIVE
