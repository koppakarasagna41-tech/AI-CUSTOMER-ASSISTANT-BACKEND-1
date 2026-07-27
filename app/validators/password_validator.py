"""
app/validators/password_validator.py
──────────────────────────────────────
Password strength and safety validation.

validate_password(password) → ValidationResult
  - Minimum/maximum length
  - Complexity requirements (uppercase, lowercase, digit, special char)
  - Common/breached password check (top-100 list)
  - No whitespace-only password
"""

from __future__ import annotations
import re
from .email_validator import ValidationResult

PASSWORD_MIN_LEN = 8
PASSWORD_MAX_LEN = 128

# Top common/breached passwords (partial list — extend as needed)
_COMMON_PASSWORDS = {
    "password", "password1", "12345678", "123456789", "qwerty123",
    "iloveyou", "admin123", "letmein", "welcome1", "monkey123",
    "dragon123", "master123", "sunshine", "princess", "football",
    "shadow123", "superman", "michael1", "jessica1", "password!",
    "abc12345", "pass1234", "qwerty1!", "test1234", "hello123",
}

_SPECIAL_CHARS = r"!@#$%^&*()_\-+=\[\]{};':\"\\|,.<>\/?`~"


def validate_password(password: str, confirm: str | None = None) -> ValidationResult:
    """
    Validate password strength.

    Args:
        password : plaintext password to validate
        confirm  : optional confirmation string (must match password)

    Returns ValidationResult with all failed rules in errors[].
    """
    errors: list[str] = []

    if not password or not isinstance(password, str):
        return ValidationResult(valid=False, errors=["Password is required."], code="PASSWORD_REQUIRED")

    if password.strip() == "":
        return ValidationResult(valid=False, errors=["Password cannot be blank."], code="PASSWORD_BLANK")

    if len(password) < PASSWORD_MIN_LEN:
        errors.append(f"Password must be at least {PASSWORD_MIN_LEN} characters.")

    if len(password) > PASSWORD_MAX_LEN:
        errors.append(f"Password must be {PASSWORD_MAX_LEN} characters or fewer.")

    if not re.search(r"[A-Z]", password):
        errors.append("Password must contain at least one uppercase letter.")

    if not re.search(r"[a-z]", password):
        errors.append("Password must contain at least one lowercase letter.")

    if not re.search(r"\d", password):
        errors.append("Password must contain at least one digit.")

    if not re.search(f"[{_SPECIAL_CHARS}]", password):
        errors.append("Password must contain at least one special character (!@#$%^&* etc.).")

    if password.lower() in _COMMON_PASSWORDS:
        errors.append("This password is too common. Please choose a stronger one.")

    if confirm is not None and password != confirm:
        errors.append("Passwords do not match.")

    if errors:
        return ValidationResult(valid=False, errors=errors, code="PASSWORD_WEAK")

    return ValidationResult(valid=True, value="[REDACTED]")


def get_strength_label(password: str) -> str:
    """Return a human-readable strength label: weak | fair | strong | very_strong."""
    score = 0
    if len(password) >= 8:  score += 1
    if len(password) >= 12: score += 1
    if re.search(r"[A-Z]", password): score += 1
    if re.search(r"[a-z]", password): score += 1
    if re.search(r"\d",    password): score += 1
    if re.search(f"[{_SPECIAL_CHARS}]", password): score += 1
    if len(password) >= 16: score += 1

    if score <= 2: return "weak"
    if score <= 4: return "fair"
    if score <= 5: return "strong"
    return "very_strong"
