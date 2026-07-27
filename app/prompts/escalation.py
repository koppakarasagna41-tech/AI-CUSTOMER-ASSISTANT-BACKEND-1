"""
app/prompts/escalation.py
──────────────────────────
Escalation prompt template.

Handles:
  - Automatic escalation (low RAG confidence)
  - Customer-requested human agent
  - Critical or legal escalation
  - Escalation handoff message generation
  - Creating context summaries for human agents
"""

from __future__ import annotations
from typing import Optional
from .base import BasePrompt


class EscalationPrompt(BasePrompt):
    """Prompt template for escalating conversations to human agents."""

    CATEGORY = "escalation"

    @classmethod
    def system(cls) -> str:
        return (
            "You are handling the escalation phase of a customer support interaction. "
            "Your role is to:\n"
            "1. Inform the customer professionally that their issue is being escalated.\n"
            "2. Set clear expectations about what happens next.\n"
            "3. Make the customer feel their issue is being taken seriously.\n"
            "4. Prepare a complete, structured handoff summary for the human agent.\n\n"

            "ESCALATION MESSAGING RULES:\n"
            "- Never say 'I can't help you' — always frame it as 'I want to make sure "
            "you get the best possible help, so I'm connecting you with a specialist.'\n"
            "- Provide realistic wait time estimates if known.\n"
            "- Confirm the customer's contact details will be passed on so they don't "
            "have to repeat themselves.\n"
            "- If a ticket ID was generated, always share it with the customer.\n"
            "- For critical/legal escalations, use a calmer, more formal tone and "
            "avoid any admissions of liability.\n\n"

            "HANDOFF SUMMARY must include:\n"
            "  • Customer name and contact\n"
            "  • Issue category\n"
            "  • Summary of the problem\n"
            "  • Steps already taken\n"
            "  • Reason for escalation\n"
            "  • Urgency level"
        )

    @classmethod
    def user(
        cls,
        *,
        customer_name: Optional[str] = None,
        reason: str,
        ticket_id: Optional[str] = None,
        urgency: str = "normal",
        estimated_wait: Optional[str] = None,
    ) -> str:
        """
        User-turn message the AI sends TO the customer during escalation.

        Args:
            customer_name  : display name
            reason         : brief reason for escalation
            ticket_id      : support ticket reference
            urgency        : 'low' | 'normal' | 'high' | 'critical'
            estimated_wait : e.g. "within 2 business hours"
        """
        greeting    = cls._name(customer_name)
        ticket_note = (
            f" Your reference number is **{ticket_id}**."
            if ticket_id else ""
        )
        wait_note   = (
            f" A specialist will reach out {estimated_wait}."
            if estimated_wait else " A specialist will follow up as soon as possible."
        )

        urgency_prefix = ""
        if urgency in ("high", "critical"):
            urgency_prefix = "This has been marked as a priority case. "

        return (
            f"{greeting}, I want to make sure you receive the best possible "
            f"assistance for this issue.\n\n"
            f"Reason for escalation: {reason}\n\n"
            f"{urgency_prefix}I am now connecting you with a human support specialist "
            f"who has full context of our conversation.{wait_note}{ticket_note}\n\n"
            "Generate a polished, empathetic escalation message to the customer based "
            "on the above. Reassure them their issue is in good hands and they will not "
            "need to repeat themselves."
        )

    @classmethod
    def handoff_summary(
        cls,
        *,
        customer_name: Optional[str] = None,
        customer_email: Optional[str] = None,
        issue_category: str,
        issue_summary: str,
        steps_taken: Optional[str] = None,
        escalation_reason: str,
        urgency: str = "normal",
        conversation_id: Optional[str] = None,
    ) -> str:
        """
        Generates the internal handoff note sent to the human agent.

        Args:
            customer_name     : display name
            customer_email    : customer email
            issue_category    : e.g. 'billing', 'technical', 'refund'
            issue_summary     : brief description of the problem
            steps_taken       : what was already tried or offered
            escalation_reason : why AI could not resolve
            urgency           : 'low' | 'normal' | 'high' | 'critical'
            conversation_id   : chat session reference
        """
        steps_block  = f"\nSteps already taken: {steps_taken}" if steps_taken else ""
        conv_block   = f"\nConversation ID: {conversation_id}" if conversation_id else ""
        email_block  = f"\nEmail: {customer_email}" if customer_email else ""

        return (
            f"AGENT HANDOFF SUMMARY\n"
            f"{'=' * 40}\n"
            f"Customer: {customer_name or 'Unknown'}"
            f"{email_block}"
            f"{conv_block}\n"
            f"Issue category: {issue_category}\n"
            f"Urgency: {urgency.upper()}\n"
            f"Issue summary: {issue_summary}"
            f"{steps_block}\n"
            f"Escalation reason: {escalation_reason}\n"
            f"{'=' * 40}\n\n"
            "Generate a clean, professional internal handoff note using the above "
            "information. The human agent should be able to immediately understand "
            "the situation and continue without asking the customer to repeat anything."
        )

    @classmethod
    def low_confidence(cls, *, question: str) -> str:
        """
        User-turn prompt when RAG confidence is below threshold.
        The AI tells the customer it cannot answer confidently.
        """
        return (
            f"The customer asked: \"{question}\"\n\n"
            "The AI support system could not find a confident answer in the knowledge "
            "base. Generate a polite, empathetic message that:\n"
            "1. Does NOT say 'I don't know' bluntly.\n"
            "2. Explains that to give the most accurate answer, you are connecting "
            "them with a specialist.\n"
            "3. Reassures them a human agent will follow up shortly.\n"
            "4. Keeps the tone warm and professional.\n"
            "Keep the message to 2–3 sentences."
        )
