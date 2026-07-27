"""
app/validators/message_validator.py
──────────────────────────────────────
Chat message validation + prompt injection prevention.

validate_message(text) → ValidationResult
  - Length bounds
  - Not empty / whitespace-only
  - Prompt injection pattern detection
  - Malicious content patterns (XSS, SQL injection, shell commands)
  - Unicode abuse (excessive invisible chars, homoglyph spam)
"""

from __future__ import annotations
import re
import unicodedata
from .email_validator import ValidationResult

MSG_MIN_LEN  = 1
MSG_MAX_LEN  = 4000

# ── Prompt injection patterns ────────────────────────────────
# These patterns attempt to override system instructions.
_PROMPT_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions?",
    r"disregard\s+(all\s+)?(previous|prior|above)\s+instructions?",
    r"forget\s+(everything|all)\s+(you\s+)?(know|were\s+told)",
    r"you\s+are\s+now\s+(a|an)\s+\w+",
    r"act\s+as\s+(if\s+you\s+are\s+)?(a|an)\s+\w+",
    r"pretend\s+(you\s+are|to\s+be)\s+(a|an)",
    r"jailbreak",
    r"dan\s+mode",
    r"developer\s+mode\s+enabled",
    r"system\s*:\s*(you\s+are|ignore|forget)",
    r"\[system\]",
    r"\[user\].*\[assistant\]",
    r"<\|system\|>",
    r"<\|im_start\|>",
    r"###\s*instruction",
    r"new\s+conversation\s+starts?\s+here",
    r"override\s+(your\s+)?(instructions?|rules?|guidelines?)",
    r"your\s+(true\s+)?(purpose|goal|mission)\s+is",
    r"reveal\s+(your\s+)?(system\s+)?(prompt|instructions?)",
    r"print\s+(your\s+)?(system\s+)?(prompt|instructions?)",
    r"what\s+are\s+your\s+instructions",
    r"show\s+me\s+your\s+(system\s+)?prompt",
]

# ── XSS / script injection ────────────────────────────────────
_XSS_PATTERNS = [
    r"<\s*script[^>]*>",
    r"javascript\s*:",
    r"on\w+\s*=\s*['\"]",
    r"<\s*iframe",
    r"<\s*object",
    r"<\s*embed",
    r"document\s*\.\s*cookie",
    r"window\s*\.\s*location",
    r"eval\s*\(",
    r"base64\s*,",
]

# ── SQL injection ─────────────────────────────────────────────
_SQL_PATTERNS = [
    r"'\s*(or|and)\s+'?1'?\s*=\s*'?1",
    r"union\s+(all\s+)?select",
    r"drop\s+(table|database|schema)",
    r"insert\s+into\s+\w+",
    r"delete\s+from\s+\w+",
    r"exec\s*\(",
    r"xp_cmdshell",
    r";\s*--",
]

# ── Shell command injection ───────────────────────────────────
_SHELL_PATTERNS = [
    r";\s*(ls|cat|rm|wget|curl|chmod|chown|nc|netcat|bash|sh|python|perl|ruby)\s",
    r"\|\s*(bash|sh|cmd|powershell)",
    r"&&\s*(rm|wget|curl|nc)\s",
    r"`[^`]+`",
    r"\$\([^)]+\)",
    r"\.\./\.\./",
    r"/etc/(passwd|shadow|hosts)",
]

_ALL_PATTERNS: list[tuple[str, str, list[str]]] = [
    ("PROMPT_INJECTION",  "Prompt injection attempt detected.",  _PROMPT_INJECTION_PATTERNS),
    ("XSS_INJECTION",     "Script injection attempt detected.",  _XSS_PATTERNS),
    ("SQL_INJECTION",     "SQL injection attempt detected.",     _SQL_PATTERNS),
    ("SHELL_INJECTION",   "Command injection attempt detected.", _SHELL_PATTERNS),
]

# Compile all patterns at import time for performance
_COMPILED: list[tuple[str, str, list[re.Pattern]]] = [
    (code, msg, [re.compile(p, re.IGNORECASE | re.DOTALL) for p in pats])
    for code, msg, pats in _ALL_PATTERNS
]

# Max ratio of invisible/control characters before rejecting
_MAX_INVISIBLE_RATIO = 0.10


def validate_message(text: str) -> ValidationResult:
    """
    Validate a chat message for length, content, and injection attacks.
    Returns ValidationResult.
    """
    if text is None or not isinstance(text, str):
        return ValidationResult(valid=False, errors=["Message is required."], code="MSG_REQUIRED")

    stripped = text.strip()

    if len(stripped) < MSG_MIN_LEN:
        return ValidationResult(valid=False, errors=["Message cannot be empty."], code="MSG_EMPTY")

    if len(text) > MSG_MAX_LEN:
        return ValidationResult(
            valid=False,
            errors=[f"Message must be {MSG_MAX_LEN} characters or fewer (got {len(text)})."],
            code="MSG_TOO_LONG",
        )

    # Unicode abuse — invisible/control character flood
    invisible = sum(
        1 for ch in text
        if unicodedata.category(ch) in ("Cf", "Cc", "Cs") or ch == "\x00"
    )
    if len(text) > 0 and invisible / len(text) > _MAX_INVISIBLE_RATIO:
        return ValidationResult(
            valid=False,
            errors=["Message contains excessive invisible or control characters."],
            code="MSG_UNICODE_ABUSE",
        )

    # Security pattern checks
    for code, human_msg, patterns in _COMPILED:
        for pat in patterns:
            if pat.search(text):
                return ValidationResult(valid=False, errors=[human_msg], code=code)

    return ValidationResult(valid=True, value=stripped)


def sanitize_message(text: str) -> str:
    """
    Light sanitisation pass — strips leading/trailing whitespace,
    collapses excessive newlines, removes null bytes.
    Does NOT escape HTML (that's the frontend's job).
    """
    if not text:
        return ""
    text = text.replace("\x00", "")
    text = re.sub(r"\n{4,}", "\n\n\n", text)  # max 3 consecutive newlines
    return text.strip()
