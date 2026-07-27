"""
app/prompts/billing.py
───────────────────────
Billing prompt template.

Handles:
  - Invoice questions
  - Duplicate charges
  - Subscription billing cycles
  - Payment method updates
  - Failed payment follow-up
"""

from __future__ import annotations
from typing import Optional
from .base import BasePrompt


class BillingPrompt(BasePrompt):
    """Prompt template for billing and payment support."""

    CATEGORY = "billing"

    @classmethod
    def system(cls) -> str:
        return (
            "You are a billing support specialist. Your role is to help customers "
            "understand their charges, resolve billing discrepancies, and guide them "
            "through payment-related issues.\n\n"

            "BILLING SUPPORT GUIDELINES:\n"
            "1. Always acknowledge the customer's billing concern with empathy and "
            "professionalism.\n"
            "2. Ask for the invoice number or account email if not provided.\n"
            "3. For duplicate charges: reassure the customer, explain that the billing "
            "team will investigate, and provide an expected resolution timeframe "
            "(typically 3–5 business days).\n"
            "4. For failed payments: explain common causes (expired card, insufficient "
            "funds, bank block) and guide them to update their payment method.\n"
            "5. For subscription billing: explain the billing cycle clearly — charges "
            "occur on the renewal date, not the purchase date.\n"
            "6. Never access or share full account financial details. Reference only "
            "partial identifiers.\n"
            "7. If a dispute requires manual review, escalate politely and provide "
            "a case reference where possible.\n\n"

            "TONE: Professional, clear, and reassuring. Customers are often stressed "
            "about money — be especially patient."
            + cls._privacy_reminder()
        )

    @classmethod
    def user(
        cls,
        *,
        customer_name: Optional[str] = None,
        issue: str,
        invoice_id: Optional[str] = None,
        charge_amount: Optional[str] = None,
        charge_date: Optional[str] = None,
        subscription_plan: Optional[str] = None,
    ) -> str:
        """
        Args:
            customer_name     : display name
            issue             : billing problem description
            invoice_id        : invoice or transaction ID
            charge_amount     : amount in question (e.g. "$29.99")
            charge_date       : date of the charge
            subscription_plan : plan name if relevant
        """
        greeting = cls._name(customer_name)

        details: list[str] = []
        if invoice_id:        details.append(f"Invoice/Transaction ID: {invoice_id}")
        if charge_amount:     details.append(f"Amount: {charge_amount}")
        if charge_date:       details.append(f"Charge date: {charge_date}")
        if subscription_plan: details.append(f"Subscription plan: {subscription_plan}")

        detail_block = (
            "\n".join(f"- {d}" for d in details)
            if details else "No additional details provided."
        )

        return (
            f"{greeting} has a billing concern:\n\n"
            f"\"{issue}\"\n\n"
            f"Details:\n{detail_block}\n\n"
            "Please address the billing issue clearly. Explain what likely happened, "
            "what the customer can do next, and if applicable, how long resolution "
            "will take."
            + cls._closing()
        )

    @classmethod
    def failed_payment(
        cls,
        *,
        customer_name: Optional[str] = None,
        plan: Optional[str] = None,
        amount: Optional[str] = None,
    ) -> str:
        """Specific user-turn for a failed payment notification."""
        greeting = cls._name(customer_name)
        plan_note = f" for the {plan} plan" if plan else ""
        amount_note = f" of {amount}" if amount else ""

        return (
            f"{greeting}'s payment{amount_note}{plan_note} has failed.\n\n"
            "Explain the most common reasons for payment failure and provide clear "
            "step-by-step instructions on how to update their payment method to avoid "
            "service interruption."
            + cls._closing()
        )
