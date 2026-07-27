"""
app/prompts/greetings.py
─────────────────────────
Greeting and conversation-opening prompt templates.

Handles:
  - First contact greetings (new session)
  - Returning customer greetings
  - Time-of-day personalised greetings
  - Post-resolution closing messages
  - Inactivity / session timeout messages
"""

from __future__ import annotations
from typing import Optional
from datetime import datetime, timezone
from .base import BasePrompt


def _time_of_day() -> str:
    """Return 'morning', 'afternoon', or 'evening' based on UTC hour."""
    hour = datetime.now(tz=timezone.utc).hour
    if hour < 12:  return "morning"
    if hour < 17:  return "afternoon"
    return "evening"


class GreetingsPrompt(BasePrompt):
    """Prompt template for greetings and conversation opening/closing."""

    CATEGORY = "greetings"

    @classmethod
    def system(cls) -> str:
        return (
            "You are the friendly, welcoming face of our customer support team. "
            "Your role in this context is to open conversations warmly, make the "
            "customer feel comfortable, and smoothly transition into understanding "
            "their needs.\n\n"

            "GREETING GUIDELINES:\n"
            "1. Always greet the customer by name when available.\n"
            "2. Keep greetings brief — 1 to 2 sentences maximum.\n"
            "3. Immediately pivot to understanding how you can help.\n"
            "4. Never use hollow corporate phrases like 'Your call is important to us.'\n"
            "5. Match the customer's energy — if they're frustrated, skip the upbeat "
            "tone; if they're relaxed, be friendly and warm.\n"
            "6. For returning customers, acknowledge their return genuinely.\n\n"

            "TONE: Warm, genuine, human. Not robotic, not overly formal, not overly "
            "casual. Think: friendly professional colleague."
        )

    @classmethod
    def user(
        cls,
        *,
        customer_name: Optional[str] = None,
        is_returning: bool = False,
        time_of_day: Optional[str] = None,
    ) -> str:
        """
        Args:
            customer_name : display name for personalisation
            is_returning  : True if this customer has prior interactions
            time_of_day   : 'morning' | 'afternoon' | 'evening' (auto-detected if None)
        """
        tod      = time_of_day or _time_of_day()
        name     = f", {customer_name}" if customer_name else ""
        welcome  = "Welcome back" if is_returning else "Welcome"

        return (
            f"{welcome}{name}! Good {tod}.\n\n"
            "Generate a warm, brief greeting that welcomes the customer and "
            "immediately invites them to share how you can help them today. "
            "Keep it to 1–2 sentences."
        )

    @classmethod
    def closing(
        cls,
        *,
        customer_name: Optional[str] = None,
        issue_resolved: bool = True,
        ticket_created: bool = False,
        ticket_id: Optional[str] = None,
    ) -> str:
        """
        User-turn prompt for closing a resolved conversation.

        Args:
            customer_name  : display name
            issue_resolved : whether the issue was fully resolved in chat
            ticket_created : whether a support ticket was created
            ticket_id      : ticket reference number if created
        """
        name_part   = f", {customer_name}" if customer_name else ""
        ticket_note = (
            f" Your support ticket {ticket_id} has been created."
            if ticket_created and ticket_id
            else (" A support ticket has been created for follow-up."
                  if ticket_created else "")
        )

        if issue_resolved:
            return (
                f"The issue for {customer_name or 'the customer'} has been resolved.\n\n"
                "Generate a warm closing message that:\n"
                "1. Confirms the issue is resolved.\n"
                "2. Invites them to return if they need further help.\n"
                "3. Wishes them well.\n"
                "Keep it genuine and brief — 2 to 3 sentences."
            )
        else:
            return (
                f"The session is ending but the issue for "
                f"{customer_name or 'the customer'} was not fully resolved."
                f"{ticket_note}\n\n"
                "Generate a closing message that:\n"
                "1. Acknowledges the issue is still being worked on.\n"
                "2. Reassures the customer that the team will follow up.\n"
                "3. Provides the ticket reference if available.\n"
                "4. Remains warm and professional."
            )

    @classmethod
    def timeout(cls, *, customer_name: Optional[str] = None) -> str:
        """User-turn prompt when a session has been inactive."""
        name = f", {customer_name}" if customer_name else ""
        return (
            f"The chat session for {customer_name or 'the customer'} has been "
            "inactive for a while.\n\n"
            f"Generate a polite, short message checking if {customer_name or 'they'} "
            "still need help. If not, offer a warm goodbye. Keep it to 1 sentence."
        )
