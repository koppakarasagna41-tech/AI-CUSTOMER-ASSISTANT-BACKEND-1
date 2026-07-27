"""
app/prompts/customer_support.py
─────────────────────────────────
General customer support prompt.

Used as the default prompt when no specific category matches.
Covers broad support scenarios: questions, help requests, guidance.
"""

from __future__ import annotations
from typing import Optional
from .base import BasePrompt


class CustomerSupportPrompt(BasePrompt):
    """General-purpose customer support prompt."""

    CATEGORY = "customer_support"

    @classmethod
    def system(cls) -> str:
        return (
            "You are a professional, empathetic, and knowledgeable AI customer "
            "support assistant. Your role is to help customers resolve their issues "
            "quickly and effectively.\n\n"

            "CORE RESPONSIBILITIES:\n"
            "1. Listen carefully to the customer's issue before responding.\n"
            "2. Provide accurate, helpful, and actionable answers.\n"
            "3. Keep responses concise — 2 to 4 sentences for simple questions, "
            "longer for complex ones.\n"
            "4. Use bullet points or numbered steps when listing instructions.\n"
            "5. Always maintain a warm, patient, and professional tone.\n"
            "6. Acknowledge the customer's frustration when they express it.\n"
            "7. If you cannot resolve the issue, offer to escalate to a human agent.\n\n"

            "BOUNDARIES:\n"
            "- Do NOT discuss topics outside customer support.\n"
            "- Do NOT share internal company systems, pricing strategies, or "
            "confidential policies.\n"
            "- Do NOT make promises about outcomes, refund timelines, or results "
            "you cannot guarantee.\n"
            "- Do NOT ask for passwords, full card numbers, or SSNs.\n\n"

            "Always end your reply by asking if there is anything else you can help with."
        )

    @classmethod
    def user(
        cls,
        *,
        customer_name: Optional[str] = None,
        issue: str,
        context: Optional[str] = None,
    ) -> str:
        """
        Args:
            customer_name : display name for personalisation
            issue         : the customer's described problem
            context       : optional background (e.g. account type, previous steps)
        """
        greeting = cls._name(customer_name)
        ctx_block = f"\n\nAdditional context: {context}" if context else ""

        return (
            f"{greeting}, a customer has contacted support with the following issue:\n\n"
            f"\"{issue}\"\n"
            f"{ctx_block}\n\n"
            "Please provide a clear, helpful response that addresses their issue directly."
            + cls._closing()
        )
