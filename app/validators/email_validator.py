"""
app/validators/email_validator.py
───────────────────────────────────
Email address validation.

validate_email_address(email) → ValidationResult
  - RFC-5321 format check
  - Blocked disposable domain list
  - Normalisation (lowercase, strip)
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field


@dataclass
class ValidationResult:
    valid:   bool
    value:   str          = ""       # normalised value on success
    errors:  list[str]   = field(default_factory=list)
    code:    str          = ""


# Basic RFC-5321 pattern (covers 99%+ of real addresses)
_EMAIL_RE = re.compile(
    r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
)

# Common disposable/throwaway domains
_BLOCKED_DOMAINS = {
    "mailinator.com", "guerrillamail.com", "tempmail.com", "throwaway.email",
    "trashmail.com", "sharklasers.com", "guerrillamailblock.com", "grr.la",
    "guerrillamail.info", "spam4.me", "yopmail.com", "dispostable.com",
    "maildrop.cc", "fakeinbox.com", "getairmail.com", "trashmail.at",
    "discard.email", "spamgourmet.com", "spamgourmet.net", "mailnull.com",
}

EMAIL_MIN_LEN  = 5
EMAIL_MAX_LEN  = 254


def validate_email_address(email: str) -> ValidationResult:
    """
    Validate and normalise an email address.

    Returns ValidationResult with:
      - valid=True, value=normalised_email   on success
      - valid=False, errors=[...], code=...  on failure
    """
    if not email or not isinstance(email, str):
        return ValidationResult(valid=False, errors=["Email is required."], code="EMAIL_REQUIRED")

    normalised = email.strip().lower()

    if len(normalised) < EMAIL_MIN_LEN:
        return ValidationResult(valid=False, errors=["Email is too short."], code="EMAIL_TOO_SHORT")

    if len(normalised) > EMAIL_MAX_LEN:
        return ValidationResult(valid=False, errors=["Email must be 254 characters or fewer."], code="EMAIL_TOO_LONG")

    if not _EMAIL_RE.match(normalised):
        return ValidationResult(valid=False, errors=["Invalid email format."], code="EMAIL_INVALID_FORMAT")

    domain = normalised.split("@")[1]
    if domain in _BLOCKED_DOMAINS:
        return ValidationResult(valid=False, errors=["Disposable email addresses are not allowed."], code="EMAIL_DISPOSABLE")

    return ValidationResult(valid=True, value=normalised)
