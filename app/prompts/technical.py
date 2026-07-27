"""
app/prompts/technical.py
─────────────────────────
Technical support prompt template.

Handles:
  - App crashes / errors
  - Login and connectivity problems
  - Feature not working as expected
  - Integration failures
  - Performance issues
"""

from __future__ import annotations
from typing import Optional
from .base import BasePrompt


class TechnicalPrompt(BasePrompt):
    """Prompt template for technical issue support."""

    CATEGORY = "technical"

    @classmethod
    def system(cls) -> str:
        return (
            "You are a skilled technical support engineer. Your role is to help "
            "customers diagnose and resolve technical issues with the product in a "
            "clear, step-by-step manner.\n\n"

            "TECHNICAL SUPPORT GUIDELINES:\n"
            "1. Start by acknowledging the issue and asking for any missing details "
            "(browser/device/OS version, error message, steps to reproduce).\n"
            "2. Follow a structured troubleshooting flow:\n"
            "   a. Confirm the exact symptoms and error messages.\n"
            "   b. Rule out common causes (cache, cookies, network, permissions).\n"
            "   c. Provide step-by-step resolution instructions.\n"
            "   d. Confirm whether the fix worked before closing.\n"
            "3. Use plain, non-technical language unless the customer indicates "
            "technical proficiency.\n"
            "4. Number every troubleshooting step clearly.\n"
            "5. If the issue requires a code fix, server-side investigation, or "
            "database access — escalate immediately with a detailed handoff note.\n"
            "6. Never guess at root causes — if uncertain, say so and escalate.\n\n"

            "COMMON FIRST STEPS TO SUGGEST:\n"
            "- Clear browser cache and cookies.\n"
            "- Try a different browser or incognito mode.\n"
            "- Check internet connection stability.\n"
            "- Disable browser extensions.\n"
            "- Log out and back in.\n"
            "- Try the mobile app vs. web app.\n\n"

            "Always confirm the issue is resolved before ending the conversation."
        )

    @classmethod
    def user(
        cls,
        *,
        customer_name: Optional[str] = None,
        issue: str,
        error_message: Optional[str] = None,
        device: Optional[str] = None,
        os_version: Optional[str] = None,
        browser: Optional[str] = None,
        steps_tried: Optional[str] = None,
    ) -> str:
        """
        Args:
            customer_name : display name
            issue         : description of the technical problem
            error_message : exact error text if available
            device        : device type (desktop, mobile, tablet)
            os_version    : operating system and version
            browser       : browser name and version
            steps_tried   : troubleshooting already attempted
        """
        greeting = cls._name(customer_name)

        env_parts: list[str] = []
        if device:     env_parts.append(f"Device: {device}")
        if os_version: env_parts.append(f"OS: {os_version}")
        if browser:    env_parts.append(f"Browser: {browser}")

        env_block = (
            "Environment:\n" + "\n".join(f"- {p}" for p in env_parts)
            if env_parts else ""
        )

        error_block = (
            f"\nError message: \"{error_message}\"" if error_message else ""
        )
        steps_block = (
            f"\nAlready tried: {steps_tried}" if steps_tried else ""
        )

        return (
            f"{greeting} is experiencing a technical issue:\n\n"
            f"\"{issue}\""
            f"{error_block}"
            f"{steps_block}\n\n"
            f"{env_block}\n\n"
            "Please provide a clear, numbered troubleshooting guide to resolve "
            "this issue. Start with the most likely causes and simplest fixes first."
            + cls._closing()
        )

    @classmethod
    def bug_report(
        cls,
        *,
        customer_name: Optional[str] = None,
        feature: str,
        expected: str,
        actual: str,
        steps_to_reproduce: Optional[str] = None,
    ) -> str:
        """User-turn prompt for a customer reporting a bug."""
        greeting = cls._name(customer_name)
        steps_block = (
            f"\nSteps to reproduce: {steps_to_reproduce}"
            if steps_to_reproduce else ""
        )

        return (
            f"{greeting} is reporting a bug in the {feature} feature.\n\n"
            f"Expected behaviour: {expected}\n"
            f"Actual behaviour: {actual}"
            f"{steps_block}\n\n"
            "Acknowledge the bug report, thank the customer, confirm you are logging "
            "it for the engineering team, and provide an estimated response time."
            + cls._closing()
        )
