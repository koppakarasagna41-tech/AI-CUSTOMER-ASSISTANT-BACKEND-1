"""
app/prompts/registry.py
────────────────────────
Central prompt registry.

Maps category strings to their prompt class so the rest of the application
can look up the right template by name — no scattered imports needed.

Usage:
    from app.prompts.registry import PromptRegistry

    # Get the class
    cls = PromptRegistry.get("billing")

    # Build prompts
    system_msg = cls.system()
    user_msg   = cls.user(customer_name="Jane", issue="double charge")

    # Or use the convenience helpers
    system, user = PromptRegistry.build(
        category="billing",
        customer_name="Jane",
        issue="double charge",
    )
"""

from __future__ import annotations
from typing import Optional, Type

from .base              import BasePrompt
from .customer_support  import CustomerSupportPrompt
from .refund            import RefundPrompt
from .billing           import BillingPrompt
from .technical         import TechnicalPrompt
from .account_recovery  import AccountRecoveryPrompt
from .complaint         import ComplaintPrompt
from .greetings         import GreetingsPrompt
from .escalation        import EscalationPrompt
from .unknown           import UnknownPrompt


# ── Registry map ─────────────────────────────────────────────

_REGISTRY: dict[str, Type[BasePrompt]] = {
    # Primary categories
    "customer_support":  CustomerSupportPrompt,
    "refund":            RefundPrompt,
    "billing":           BillingPrompt,
    "technical":         TechnicalPrompt,
    "account_recovery":  AccountRecoveryPrompt,
    "complaint":         ComplaintPrompt,
    "greetings":         GreetingsPrompt,
    "escalation":        EscalationPrompt,
    "unknown":           UnknownPrompt,

    # Aliases — common alternative names map to the same class
    "general":           CustomerSupportPrompt,
    "support":           CustomerSupportPrompt,
    "payment":           BillingPrompt,
    "invoice":           BillingPrompt,
    "charge":            BillingPrompt,
    "password":          AccountRecoveryPrompt,
    "login":             AccountRecoveryPrompt,
    "locked":            AccountRecoveryPrompt,
    "bug":               TechnicalPrompt,
    "error":             TechnicalPrompt,
    "crash":             TechnicalPrompt,
    "welcome":           GreetingsPrompt,
    "greeting":          GreetingsPrompt,
    "farewell":          GreetingsPrompt,
    "feedback":          ComplaintPrompt,
    "dissatisfied":      ComplaintPrompt,
    "angry":             ComplaintPrompt,
    "human":             EscalationPrompt,
    "agent":             EscalationPrompt,
    "out_of_scope":      UnknownPrompt,
    "unclear":           UnknownPrompt,
    "off_topic":         UnknownPrompt,
}

# Ordered list used for category selection / display
CATEGORIES: list[str] = [
    "customer_support",
    "refund",
    "billing",
    "technical",
    "account_recovery",
    "complaint",
    "greetings",
    "escalation",
    "unknown",
]


class PromptRegistry:
    """
    Central lookup and factory for all prompt templates.
    """

    @staticmethod
    def get(category: str) -> Type[BasePrompt]:
        """
        Return the prompt class for the given category string.

        Falls back to CustomerSupportPrompt for unrecognised categories.
        Never raises — always returns a usable class.

        Args:
            category : category name or alias (case-insensitive)

        Returns:
            A BasePrompt subclass (not an instance)
        """
        key = category.lower().strip().replace("-", "_").replace(" ", "_")
        return _REGISTRY.get(key, CustomerSupportPrompt)

    @staticmethod
    def system(category: str) -> str:
        """
        Return the system prompt string for the given category.

        Args:
            category : category name or alias

        Returns:
            System prompt string
        """
        return PromptRegistry.get(category).system()

    @staticmethod
    def build(
        category: str,
        **user_kwargs,
    ) -> tuple[str, str]:
        """
        Build (system_prompt, user_message) for a given category.

        Args:
            category    : category name or alias
            **user_kwargs: keyword args forwarded to the prompt's user() method

        Returns:
            (system_prompt: str, user_message: str)

        Example:
            system, user = PromptRegistry.build(
                "billing",
                customer_name="Jane",
                issue="I was charged twice this month.",
                invoice_id="INV-2026-0042",
            )
        """
        cls = PromptRegistry.get(category)
        return cls.system(), cls.user(**user_kwargs)

    @staticmethod
    def list_categories() -> list[str]:
        """Return the canonical list of supported category names."""
        return CATEGORIES.copy()

    @staticmethod
    def is_valid(category: str) -> bool:
        """Return True if the category resolves to a non-default class."""
        key = category.lower().strip().replace("-", "_").replace(" ", "_")
        return key in _REGISTRY
