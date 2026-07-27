"""
app/validators/user_input_validator.py
────────────────────────────────────────
General user input validation for names, text fields, IDs, URLs.

Provides:
  validate_name()        — full name / display name
  validate_text_field()  — generic short/long text
  validate_object_id()   — MongoDB ObjectId string
  validate_url()         — HTTP/HTTPS URL
  validate_search_query()— search input with injection protection
  validate_tags()        — list of tag strings
"""

from __future__ import annotations
import re
from bson import ObjectId
from bson.errors import InvalidId
from .email_validator import ValidationResult
from .message_validator import _COMPILED as _INJECTION_PATTERNS


# ── Name ──────────────────────────────────────────────────────

NAME_MIN  = 2
NAME_MAX  = 100
_NAME_RE  = re.compile(r"^[\w\s'\-\.À-ÖØ-öø-ÿ]+$", re.UNICODE)


def validate_name(name: str, field_label: str = "Name") -> ValidationResult:
    if not name or not isinstance(name, str):
        return ValidationResult(valid=False, errors=[f"{field_label} is required."], code="NAME_REQUIRED")

    stripped = name.strip()

    if len(stripped) < NAME_MIN:
        return ValidationResult(valid=False, errors=[f"{field_label} must be at least {NAME_MIN} characters."], code="NAME_TOO_SHORT")

    if len(stripped) > NAME_MAX:
        return ValidationResult(valid=False, errors=[f"{field_label} must be {NAME_MAX} characters or fewer."], code="NAME_TOO_LONG")

    if not _NAME_RE.match(stripped):
        return ValidationResult(
            valid=False,
            errors=[f"{field_label} contains invalid characters. Only letters, spaces, hyphens, and apostrophes are allowed."],
            code="NAME_INVALID_CHARS",
        )

    return ValidationResult(valid=True, value=stripped)


# ── Generic text field ────────────────────────────────────────

def validate_text_field(
    text:        str,
    field_label: str  = "Field",
    min_len:     int  = 1,
    max_len:     int  = 5000,
    required:    bool = True,
) -> ValidationResult:
    """Validate any free-text field with length bounds + injection check."""
    if not text or not isinstance(text, str):
        if required:
            return ValidationResult(valid=False, errors=[f"{field_label} is required."], code="FIELD_REQUIRED")
        return ValidationResult(valid=True, value="")

    stripped = text.strip()

    if required and len(stripped) < min_len:
        return ValidationResult(
            valid=False,
            errors=[f"{field_label} must be at least {min_len} character(s)."],
            code="FIELD_TOO_SHORT",
        )

    if len(stripped) > max_len:
        return ValidationResult(
            valid=False,
            errors=[f"{field_label} must be {max_len} characters or fewer."],
            code="FIELD_TOO_LONG",
        )

    # Light injection check on user-facing fields
    for code, human_msg, patterns in _INJECTION_PATTERNS:
        if code in ("XSS_INJECTION", "SQL_INJECTION", "SHELL_INJECTION"):
            for pat in patterns:
                if pat.search(stripped):
                    return ValidationResult(valid=False, errors=[human_msg], code=code)

    return ValidationResult(valid=True, value=stripped)


# ── MongoDB ObjectId ──────────────────────────────────────────

def validate_object_id(value: str, field_label: str = "ID") -> ValidationResult:
    """Validate a MongoDB 24-hex-char ObjectId string."""
    if not value or not isinstance(value, str):
        return ValidationResult(valid=False, errors=[f"{field_label} is required."], code="ID_REQUIRED")

    try:
        ObjectId(value.strip())
        return ValidationResult(valid=True, value=value.strip())
    except (InvalidId, TypeError):
        return ValidationResult(
            valid=False,
            errors=[f"{field_label} is not a valid identifier."],
            code="ID_INVALID",
        )


# ── URL ───────────────────────────────────────────────────────

_URL_RE = re.compile(
    r"^https?://"                         # http:// or https://
    r"(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+"
    r"[A-Z]{2,}"                          # domain
    r"(?::\d+)?"                          # optional port
    r"(?:/[^\s]*)?$",                     # optional path
    re.IGNORECASE,
)

URL_MAX = 2000


def validate_url(url: str, field_label: str = "URL") -> ValidationResult:
    """Validate an HTTP/HTTPS URL."""
    if not url or not isinstance(url, str):
        return ValidationResult(valid=False, errors=[f"{field_label} is required."], code="URL_REQUIRED")

    stripped = url.strip()

    if len(stripped) > URL_MAX:
        return ValidationResult(valid=False, errors=[f"{field_label} is too long."], code="URL_TOO_LONG")

    if not _URL_RE.match(stripped):
        return ValidationResult(
            valid=False,
            errors=[f"Invalid URL. Must start with http:// or https://."],
            code="URL_INVALID",
        )

    # Block localhost / internal IPs
    blocked_hosts = ("localhost", "127.", "192.168.", "10.", "172.16.", "::1", "0.0.0.0")
    lower = stripped.lower()
    if any(b in lower for b in blocked_hosts):
        return ValidationResult(
            valid=False,
            errors=["URLs pointing to internal/local addresses are not allowed."],
            code="URL_INTERNAL",
        )

    return ValidationResult(valid=True, value=stripped)


# ── Search query ──────────────────────────────────────────────

SEARCH_MAX = 200


def validate_search_query(query: str) -> ValidationResult:
    """Validate and sanitise a search query string."""
    if not query or not isinstance(query, str):
        return ValidationResult(valid=False, errors=["Search query is required."], code="SEARCH_REQUIRED")

    stripped = query.strip()

    if len(stripped) < 2:
        return ValidationResult(valid=False, errors=["Search query must be at least 2 characters."], code="SEARCH_TOO_SHORT")

    if len(stripped) > SEARCH_MAX:
        return ValidationResult(valid=False, errors=[f"Search query must be {SEARCH_MAX} characters or fewer."], code="SEARCH_TOO_LONG")

    # Injection check
    for code, human_msg, patterns in _INJECTION_PATTERNS:
        for pat in patterns:
            if pat.search(stripped):
                return ValidationResult(valid=False, errors=["Invalid search query."], code="SEARCH_INJECTION")

    return ValidationResult(valid=True, value=stripped)


# ── Tags ──────────────────────────────────────────────────────

TAG_MAX_LEN   = 50
TAG_MAX_COUNT = 20
_TAG_RE       = re.compile(r"^[a-zA-Z0-9_\-]+$")


def validate_tags(tags: list) -> ValidationResult:
    """Validate a list of tag strings."""
    if not isinstance(tags, list):
        return ValidationResult(valid=False, errors=["Tags must be a list."], code="TAGS_INVALID_TYPE")

    if len(tags) > TAG_MAX_COUNT:
        return ValidationResult(
            valid=False,
            errors=[f"Maximum {TAG_MAX_COUNT} tags allowed."],
            code="TAGS_TOO_MANY",
        )

    cleaned: list[str] = []
    for tag in tags:
        if not isinstance(tag, str):
            return ValidationResult(valid=False, errors=["Each tag must be a string."], code="TAG_INVALID_TYPE")
        t = tag.strip().lower()
        if len(t) > TAG_MAX_LEN:
            return ValidationResult(
                valid=False,
                errors=[f"Tag '{t[:20]}...' exceeds {TAG_MAX_LEN} characters."],
                code="TAG_TOO_LONG",
            )
        if not _TAG_RE.match(t):
            return ValidationResult(
                valid=False,
                errors=[f"Tag '{t}' contains invalid characters. Use letters, numbers, hyphens, and underscores only."],
                code="TAG_INVALID_CHARS",
            )
        cleaned.append(t)

    return ValidationResult(valid=True, value=list(dict.fromkeys(cleaned)))  # deduplicate
