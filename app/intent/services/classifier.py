"""
app/intent/services/classifier.py
────────────────────────────────────
Gemini-powered intent classifier.

How it works:
  1. Builds a structured classification prompt listing all 8 intents
     with descriptions and few-shot examples.
  2. Calls Gemini with temperature=0 for deterministic output.
  3. Gemini returns a JSON block with a score (0–1) for each intent.
  4. We parse + normalise the scores, pick the winner, and apply the
     confidence threshold.
  5. If confidence < threshold → intent is set to "unknown" (fallback).
  6. Returns an IntentResult dataclass.

Design: no business logic — pure classification. Callers decide what
to do with the result (persist, route, escalate, etc.).
"""

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Optional

import google.generativeai as genai

from app.config    import settings
from app.intent.constants import Intent, INTENT_META

logger = logging.getLogger(__name__)

# ── Configure Gemini once ─────────────────────────────────────
_configured = False


def _ensure_configured() -> None:
    global _configured
    if not _configured:
        if not settings.GEMINI_API_KEY or settings.GEMINI_API_KEY.startswith("your-"):
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Add it to your .env file."
            )
        genai.configure(api_key=settings.GEMINI_API_KEY)
        _configured = True


# ── Result dataclass ──────────────────────────────────────────

@dataclass
class ClassificationResult:
    """Raw result from the classifier before any persistence."""
    message:         str
    intent:          str
    label:           str
    confidence:      float
    is_confident:    bool
    all_scores:      dict[str, float]        # intent → score
    prompt_category: str
    model_used:      str
    tokens_used:     int  = 0
    latency_ms:      float = 0.0
    is_fallback:     bool  = False


# ── Classification prompt ─────────────────────────────────────

def _build_classification_prompt() -> str:
    """
    System prompt that instructs Gemini to classify messages into one
    of the 8 supported intents and return a structured JSON response.
    """
    intents_block = "\n".join(
        f"- \"{k}\": {v['description']}\n"
        f"  Examples: {', '.join(repr(e) for e in v['examples'][:2])}"
        for k, v in INTENT_META.items()
        if k != Intent.UNKNOWN
    )

    return (
        "You are an intent classification engine for a customer support system.\n\n"
        "TASK: Classify the customer message into exactly ONE of the following intents "
        "and return a confidence score (0.0–1.0) for EACH intent.\n\n"
        f"INTENTS:\n{intents_block}\n\n"
        "OUTPUT FORMAT — return ONLY valid JSON, no explanation, no markdown fences:\n"
        "{\n"
        '  "greeting": 0.05,\n'
        '  "question": 0.10,\n'
        '  "complaint": 0.05,\n'
        '  "refund_request": 0.70,\n'
        '  "technical_issue": 0.03,\n'
        '  "billing": 0.05,\n'
        '  "feedback": 0.01,\n'
        '  "goodbye": 0.01\n'
        "}\n\n"
        "RULES:\n"
        "1. All scores must sum to approximately 1.0.\n"
        "2. Assign the highest score to the SINGLE best-matching intent.\n"
        "3. Return ONLY the JSON object — no other text.\n"
        "4. Use exactly the intent keys listed above (lowercase with underscores)."
    )


# ── Main classifier function ──────────────────────────────────

async def classify_intent(
    message:    str,
    threshold:  Optional[float] = None,
) -> ClassificationResult:
    """
    Classify a customer message using Gemini.

    Args:
        message   : raw customer message text
        threshold : confidence threshold (defaults to settings.INTENT_CONFIDENCE_THRESHOLD)

    Returns:
        ClassificationResult with intent, confidence, and all scores.
        Never raises — returns fallback result on any Gemini failure.
    """
    _threshold  = threshold if threshold is not None else settings.INTENT_CONFIDENCE_THRESHOLD
    model_name  = settings.INTENT_MODEL
    start       = time.perf_counter()

    try:
        _ensure_configured()
    except RuntimeError as exc:
        logger.warning("Intent classifier not configured: %s", exc)
        return _fallback_result(message, model_name, start, reason="not_configured")

    def _blocking() -> tuple[str, int]:
        gen_config = genai.types.GenerationConfig(
            max_output_tokens=256,
            temperature=settings.INTENT_TEMPERATURE,
            top_p=0.1,
            top_k=1,
        )
        model  = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=_build_classification_prompt(),
            generation_config=gen_config,
        )
        result = model.generate_content(message)
        text   = result.text or ""
        tokens = getattr(result.usage_metadata, "total_token_count", 0) or 0
        return text.strip(), tokens

    try:
        raw_text, tokens_used = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(None, _blocking),
            timeout=float(settings.INTENT_TIMEOUT),
        )
    except asyncio.TimeoutError:
        logger.warning("Intent classification timed out for: %.60s", message)
        return _fallback_result(message, model_name, start, reason="timeout")
    except Exception as exc:
        logger.error("Intent classification failed: %s", exc)
        return _fallback_result(message, model_name, start, reason="api_error")

    # ── Parse JSON response ───────────────────────────────────
    scores = _parse_scores(raw_text)
    if not scores:
        logger.warning("Could not parse intent scores from: %.100s", raw_text)
        return _fallback_result(message, model_name, start, reason="parse_error")

    # ── Normalise scores to sum=1 ─────────────────────────────
    total = sum(scores.values()) or 1.0
    scores = {k: round(v / total, 4) for k, v in scores.items()}

    # ── Pick winner ───────────────────────────────────────────
    top_intent = max(scores, key=scores.get)
    top_score  = scores[top_intent]
    latency    = round((time.perf_counter() - start) * 1000, 2)

    # Apply threshold
    is_confident = top_score >= _threshold
    final_intent = top_intent if is_confident else Intent.UNKNOWN

    meta = INTENT_META.get(final_intent, INTENT_META[Intent.UNKNOWN])

    logger.info(
        "Intent classified | intent=%s score=%.3f confident=%s latency=%.1fms msg=%.50s",
        final_intent, top_score, is_confident, latency, message,
    )

    return ClassificationResult(
        message=message,
        intent=final_intent,
        label=meta["label"],
        confidence=top_score,
        is_confident=is_confident,
        all_scores=scores,
        prompt_category=meta["prompt_category"],
        model_used=model_name,
        tokens_used=tokens_used,
        latency_ms=latency,
        is_fallback=not is_confident,
    )


# ── Parser ────────────────────────────────────────────────────

def _parse_scores(text: str) -> dict[str, float]:
    """
    Extract the JSON scores dict from Gemini's response.
    Handles extra whitespace, markdown fences, or stray text.
    """
    # Strip possible ```json ... ``` fences
    text = re.sub(r"```(?:json)?", "", text).strip()

    # Extract the first {...} block
    match = re.search(r"\{[^{}]+\}", text, re.DOTALL)
    if not match:
        return {}

    try:
        raw = json.loads(match.group())
    except json.JSONDecodeError:
        return {}

    valid_keys = set(Intent.all_values()) - {Intent.UNKNOWN}
    scores: dict[str, float] = {}

    for key in valid_keys:
        val = raw.get(key)
        if val is not None:
            try:
                scores[key] = float(val)
            except (TypeError, ValueError):
                scores[key] = 0.0

    # Ensure all keys are present
    for key in valid_keys:
        scores.setdefault(key, 0.0)

    return scores


# ── Fallback result ───────────────────────────────────────────

def _fallback_result(
    message:    str,
    model_name: str,
    start:      float,
    reason:     str = "unknown",
) -> ClassificationResult:
    """Return a safe fallback when classification fails."""
    latency = round((time.perf_counter() - start) * 1000, 2)
    meta    = INTENT_META[Intent.UNKNOWN]
    # Give equal small scores to all intents
    valid   = [k for k in Intent.all_values() if k != Intent.UNKNOWN]
    scores  = {k: round(1.0 / len(valid), 4) for k in valid}

    logger.info(
        "Intent fallback | reason=%s latency=%.1fms msg=%.50s",
        reason, latency, message,
    )

    return ClassificationResult(
        message=message,
        intent=Intent.UNKNOWN,
        label=meta["label"],
        confidence=0.0,
        is_confident=False,
        all_scores=scores,
        prompt_category=meta["prompt_category"],
        model_used=model_name,
        tokens_used=0,
        latency_ms=latency,
        is_fallback=True,
    )
