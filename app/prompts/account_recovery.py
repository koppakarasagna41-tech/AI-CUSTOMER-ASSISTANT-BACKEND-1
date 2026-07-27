"""
app/prompts/account_recovery.py
─────────────────────────────────
Account recovery prompt template.

Handles:
  - Forgotten password
  - Locked / suspended accounts
  - Email address change
  - Two-factor authentication issues
  - Account takeover / unauthorized access
"""

from __future__ import annotations
from typing import Optional
from .base import BasePrompt


class AccountRecoveryPrompt(BasePrompt):
    """Prompt template for account access and recovery issues."""

    CATEGORY = "account_recovery"

    @classmethod
    def system(cls) -> str:
        return (
            "You are an account security and recovery specialist. Your role is to "
            "guide customers through the process of regaining access to their account "
            "safely and securely.\n\n"

            "ACCOUNT RECOVERY GUIDELINES:\n"
            "1. Always verify intent — ask the customer to confirm the email address "
            "associated with the account (do NOT ask for the password).\n"
            "2. For forgotten passwords:\n"
            "   - Direct them to the 'Forgot Password' link on the login page.\n"
            "   - Explain the reset email may take up to 5 minutes and to check spam.\n"
            "3. For locked accounts:\n"
            "   - Explain accounts are temporarily locked after multiple failed "
            "attempts for security.\n"
            "   - Advise waiting 15–30 minutes or using the password reset flow.\n"
            "4. For 2FA issues:\n"
            "   - Ask if they have access to their recovery codes.\n"
            "   - If not, escalate to human verification — never bypass 2FA manually.\n"
            "5. For suspected unauthorized access:\n"
            "   - Treat this as URGENT. Advise the customer to reset their password "
            "immediately and enable 2FA.\n"
            "   - Escalate to the security team right away.\n"
            "6. NEVER disable security features, bypass verification, or confirm "
            "account ownership based solely on chat messages.\n\n"

            "SECURITY FIRST: When in doubt, escalate to a human agent with ID "
            "verification capability. Do not unlock accounts based on chat alone."
            + cls._privacy_reminder()
        )

    @classmethod
    def user(
        cls,
        *,
        customer_name: Optional[str] = None,
        issue: str,
        account_email: Optional[str] = None,
        issue_type: Optional[str] = None,
    ) -> str:
        """
        Args:
            customer_name : display name
            issue         : description of the access problem
            account_email : redacted account email for reference (e.g. j***@gmail.com)
            issue_type    : 'forgotten_password' | 'locked' | '2fa' | 'unauthorized'
        """
        greeting = cls._name(customer_name)

        email_note = (
            f"\nAccount email on file: {account_email}"
            if account_email else ""
        )
        type_note = (
            f"\nIssue type: {issue_type.replace('_', ' ').title()}"
            if issue_type else ""
        )

        return (
            f"{greeting} needs help accessing their account.\n\n"
            f"Issue: \"{issue}\""
            f"{email_note}"
            f"{type_note}\n\n"
            "Guide the customer through the appropriate account recovery steps. "
            "Prioritise security — never skip verification steps."
            + cls._closing()
        )

    @classmethod
    def unauthorized_access(
        cls,
        *,
        customer_name: Optional[str] = None,
        details: Optional[str] = None,
    ) -> str:
        """Urgent user-turn prompt for suspected unauthorized account access."""
        greeting = cls._name(customer_name)
        detail_note = f"\n\nDetails: {details}" if details else ""

        return (
            f"URGENT: {greeting} believes their account has been accessed without "
            f"their permission.{detail_note}\n\n"
            "Respond with urgency. Immediately guide the customer to:\n"
            "1. Change their password right now.\n"
            "2. Enable two-factor authentication if not already active.\n"
            "3. Review recent login activity.\n"
            "4. Revoke any unknown active sessions.\n\n"
            "Escalate this to the security team for further investigation and "
            "provide a case reference number."
        )
