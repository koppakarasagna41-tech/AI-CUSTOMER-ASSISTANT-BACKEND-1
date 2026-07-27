"""
app/prompts/base.py
────────────────────
Base class and shared utilities for all prompt templates.

Every prompt template inherits from BasePrompt and implements:
  - system()     → str   — system-level instructions (injected once)
  - user(**kw)   → str   — user-turn message (parameterised)

Usage pattern:
    from app.prompts.refund import RefundPrompt

    system_msg  = RefundPrompt.system()
    user_msg    = RefundPrompt.user(
        customer_name="Jane",
        order_id="ORD-1234",
        issue="charged twice",
    )
"""

from __future__ import annotations
from typing import Optional


class BasePrompt:
    """
    Abstract base for all prompt templates.

    Rules every subclass must follow:
      1. system() returns a string — no side effects, no external calls.
      2. user()   accepts only keyword arguments so call-sites are explicit.
      3. Neither method hard-codes business data — pass it as parameters.
      4. Never include passwords, card numbers, or PII in a prompt template.
    """

    # Subclasses override this to identify themselves
    CATEGORY: str = "general"

    @classmethod
    def system(cls) -> str:
        """Return the system-level instructions for this prompt category."""
        raise NotImplementedError(f"{cls.__name__} must implement system()")

    @classmethod
    def user(cls, **kwargs) -> str:
        """Return the user-turn message, filled with the provided kwargs."""
        raise NotImplementedError(f"{cls.__name__} must implement user()")

    # ── Shared helpers ────────────────────────────────────────

    @staticmethod
    def _name(customer_name: Optional[str]) -> str:
        """Return 'Hi {name}' greeting or generic fallback."""
        return f"Hi {customer_name}" if customer_name else "Hello"

    @staticmethod
    def _closing() -> str:
        """Standard closing line appended to most user messages."""
        return "\n\nIs there anything else I can help you with today?"

    @staticmethod
    def _privacy_reminder() -> str:
        """Reminder injected when the topic might tempt the AI to ask for secrets."""
        return (
            "\n\nIMPORTANT: Never ask the customer for passwords, full credit card "
            "numbers, CVV codes, or government ID numbers. Ask only for the last "
            "4 digits of a card or the last 3 of an account number if necessary."
        )
