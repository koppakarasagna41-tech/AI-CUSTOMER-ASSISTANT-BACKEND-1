"""
app/services/ticket_classifier.py
────────────────────────────────────
Gemini-powered ticket category classifier + priority engine.

classify_ticket()     → TicketClassification dataclass
  - Calls Gemini with temperature=0 to classify subject+description
    into one of 7 categories.
  - Returns category, confidence score, and auto-assigned priority.

auto_priority()       → TicketPriority
  - Rule-based priority derived from category + keyword signals.
  - Used as a fallback when Gemini is unavailable.

Category → Default Priority mapping:
  technical        → high      (users blocked)
  billing          → high      (money at risk)
  refund           → high      (financial)
  account          → high      (access blocked)
  complaint        → medium
  feature_request  → low
  general_inquiry  → low
"""

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Optional

import google.generativeai as genai

from app.config            import settings
from app.models.ticket     import TicketCategory, TicketPriority

logger = logging.getLogger(__name__)

# ── Gemini config flag ────────────────────────────────────────
_configured = False


def _ensure_configured() -> None:
    global _configured
    if not _configured:
        if not settings.GEMINI_API_KEY or settings.GEMINI_API_KEY.startswith("your-"):
            raise RuntimeError("GEMINI_API_KEY not set.")
        genai.configure(api_key=settings.GEMINI_API_KEY)
        _configured = True


# ── Result dataclass ──────────────────────────────────────────

@dataclass
class TicketClassification:
    category:    TicketCategory
    confidence:  float
    priority:    TicketPriority
    model_used:  str
    tokens_used: int   = 0
    latency_ms:  float = 0.0
    is_fallback: bool  = False


# ── Category metadata ─────────────────────────────────────────

CATEGORY_META: dict[str, dict] = {
    TicketCategory.TECHNICAL: {
        "description": "Software bugs, errors, crashes, app not working, integrations failing.",
        "examples":    ["App crashes on login", "API returning 500 error", "Feature broken"],
        "default_priority": TicketPriority.HIGH,
        "keywords":    ["error", "crash", "broken", "not working", "bug", "500", "failed", "cannot", "can't", "issue"],
    },
    TicketCategory.BILLING: {
        "description": "Invoice questions, charge disputes, payment failures, subscription billing.",
        "examples":    ["Charged twice this month", "Payment declined", "Wrong invoice amount"],
        "default_priority": TicketPriority.HIGH,
        "keywords":    ["charge", "charged", "invoice", "payment", "billing", "subscription", "overcharged", "fee"],
    },
    TicketCategory.REFUND: {
        "description": "Refund requests, return requests, money-back requests.",
        "examples":    ["I want a refund", "Please return my money", "Cancel and refund"],
        "default_priority": TicketPriority.HIGH,
        "keywords":    ["refund", "return", "money back", "cancel", "reimburs"],
    },
    TicketCategory.ACCOUNT: {
        "description": "Account access, password reset, locked accounts, profile issues.",
        "examples":    ["Can't log in", "Account locked", "Reset my password"],
        "default_priority": TicketPriority.HIGH,
        "keywords":    ["account", "login", "password", "locked", "access", "sign in", "2fa", "two-factor"],
    },
    TicketCategory.COMPLAINT: {
        "description": "Customer dissatisfaction, poor service experience, formal complaints.",
        "examples":    ["Terrible service", "Very disappointed", "I want to escalate"],
        "default_priority": TicketPriority.MEDIUM,
        "keywords":    ["complaint", "disappointed", "terrible", "unacceptable", "frustrated", "angry", "escalate"],
    },
    TicketCategory.FEATURE_REQUEST: {
        "description": "Suggestions for new features, product improvements, enhancement requests.",
        "examples":    ["Please add dark mode", "Would be great if you added...", "Feature suggestion"],
        "default_priority": TicketPriority.LOW,
        "keywords":    ["feature", "suggestion", "add", "improvement", "would be nice", "request", "enhance"],
    },
    TicketCategory.GENERAL_INQUIRY: {
        "description": "General questions, information requests, how-to questions.",
        "examples":    ["How do I export data?", "What are your business hours?", "Where is the settings page?"],
        "default_priority": TicketPriority.LOW,
        "keywords":    ["how", "where", "what", "when", "question", "info", "help"],
    },
}


# ── Priority escalation keywords ──────────────────────────────

_CRITICAL_KEYWORDS = ["urgent", "asap", "immediately", "emergency", "critical", "data loss", "breach", "security"]
_HIGH_KEYWORDS     = ["not working", "broken", "blocked", "cannot access", "deadline", "production"]


# ── Gemini system prompt ──────────────────────────────────────

def _build_classification_prompt() -> str:
    cats_block = "\n".join(
        f'- "{k}": {v["description"]}\n'
        f'  Examples: {", ".join(repr(e) for e in v["examples"][:2])}'
        for k, v in CATEGORY_META.items()
    )

    return (
        "You are a ticket classification engine for a customer support system.\n\n"
        "TASK: Classify the support ticket into EXACTLY ONE of the following categories "
        "and return a confidence score (0.0–1.0) for each.\n\n"
        f"CATEGORIES:\n{cats_block}\n\n"
        "OUTPUT FORMAT — return ONLY valid JSON, no markdown, no explanation:\n"
        "{\n"
        '  "technical": 0.05,\n'
        '  "billing": 0.05,\n'
        '  "refund": 0.70,\n'
        '  "account": 0.05,\n'
        '  "general_inquiry": 0.05,\n'
        '  "complaint": 0.05,\n'
        '  "feature_request": 0.05\n'
        "}\n\n"
        "RULES:\n"
        "1. All scores must sum to approximately 1.0.\n"
        "2. Highest score = winning category.\n"
        "3. Return ONLY the JSON object.\n"
        "4. Use exactly the category keys shown above."
    )


# ── Main classifier ───────────────────────────────────────────

async def classify_ticket(
    subject:     str,
    description: Optional[str] = None,
) -> TicketClassification:
    """
    Classify a ticket using Gemini.
    Falls back to rule-based classification on any failure.

    Args:
        subject     : ticket subject line
        description : optional ticket body

    Returns:
        TicketClassification with category, confidence, priority, and metadata.
        Never raises.
    """
    model_name = settings.INTENT_MODEL
    start      = time.perf_counter()
    text       = subject + (" " + description if description else "")

    try:
        _ensure_configured()
    except RuntimeError:
        return _rule_based(text, model_name, start)

    def _blocking() -> tuple[str, int]:
        gen_config = genai.types.GenerationConfig(
            max_output_tokens=200,
            temperature=0.0,
            top_p=0.1,
            top_k=1,
        )
        model  = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=_build_classification_prompt(),
            generation_config=gen_config,
        )
        result = model.generate_content(text)
        raw    = result.text or ""
        tokens = getattr(result.usage_metadata, "total_token_count", 0) or 0
        return raw.strip(), tokens

    try:
        raw_text, tokens_used = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(None, _blocking),
            timeout=float(settings.INTENT_TIMEOUT),
        )
    except (asyncio.TimeoutError, Exception) as exc:
        logger.warning("Ticket classification error: %s — using rule-based fallback", exc)
        return _rule_based(text, model_name, start)

    scores = _parse_scores(raw_text)
    if not scores:
        return _rule_based(text, model_name, start)

    # Normalise
    total  = sum(scores.values()) or 1.0
    scores = {k: round(v / total, 4) for k, v in scores.items()}

    top_cat   = max(scores, key=scores.get)
    top_score = scores[top_cat]
    latency   = round((time.perf_counter() - start) * 1000, 2)

    category = TicketCategory(top_cat)
    priority = auto_priority(text, category)

    logger.info(
        "Ticket classified | category=%s confidence=%.3f priority=%s latency=%.1fms",
        category, top_score, priority, latency,
    )

    return TicketClassification(
        category=category,
        confidence=top_score,
        priority=priority,
        model_used=model_name,
        tokens_used=tokens_used,
        latency_ms=latency,
        is_fallback=False,
    )


# ── Priority engine ───────────────────────────────────────────

def auto_priority(text: str, category: TicketCategory) -> TicketPriority:
    """
    Derive priority from category default + keyword escalation signals.

    Escalation rules:
      - Any critical keyword  → CRITICAL
      - Any high keyword      → HIGH (unless already critical)
      - Category default      → as defined in CATEGORY_META
    """
    lower = text.lower()

    if any(kw in lower for kw in _CRITICAL_KEYWORDS):
        return TicketPriority.CRITICAL

    if any(kw in lower for kw in _HIGH_KEYWORDS):
        return TicketPriority.HIGH

    return CATEGORY_META[category]["default_priority"]


# ── Helpers ───────────────────────────────────────────────────

def _parse_scores(text: str) -> dict[str, float]:
    text  = re.sub(r"```(?:json)?", "", text).strip()
    match = re.search(r"\{[^{}]+\}", text, re.DOTALL)
    if not match:
        return {}
    try:
        raw = json.loads(match.group())
    except json.JSONDecodeError:
        return {}

    valid  = {c.value for c in TicketCategory}
    scores: dict[str, float] = {}
    for key in valid:
        val = raw.get(key)
        try:
            scores[key] = float(val) if val is not None else 0.0
        except (TypeError, ValueError):
            scores[key] = 0.0
    return scores


def _rule_based(
    text:       str,
    model_name: str,
    start:      float,
) -> TicketClassification:
    """Keyword-based fallback when Gemini is unavailable."""
    lower  = text.lower()
    best   = TicketCategory.GENERAL_INQUIRY
    best_n = 0

    for cat, meta in CATEGORY_META.items():
        n = sum(1 for kw in meta["keywords"] if kw in lower)
        if n > best_n:
            best_n = n
            best   = TicketCategory(cat)

    latency = round((time.perf_counter() - start) * 1000, 2)
    priority = auto_priority(text, best)

    logger.info(
        "Ticket rule-based | category=%s priority=%s latency=%.1fms",
        best, priority, latency,
    )

    return TicketClassification(
        category=best,
        confidence=0.5 if best_n > 0 else 0.2,
        priority=priority,
        model_used=f"{model_name}(rule-based)",
        tokens_used=0,
        latency_ms=latency,
        is_fallback=True,
    )
