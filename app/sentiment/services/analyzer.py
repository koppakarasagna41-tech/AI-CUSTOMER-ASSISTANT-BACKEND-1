"""
app/sentiment/services/analyzer.py
─────────────────────────────────────
Gemini-powered sentiment analyzer.

Pipeline:
  1. Build a structured classification prompt for 4 sentiment classes.
  2. Call Gemini (temperature=0) — returns JSON scores for each class.
  3. Parse + normalise scores; pick the winner.
  4. If confidence < threshold → fallback to "neutral".
  5. Return AnalysisResult dataclass — never raises.

Rule-based fallback runs when Gemini is unavailable (no API key /
timeout / parse failure) using a keyword lexicon.
"""

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Optional

import google.generativeai as genai

from app.config               import settings
from app.sentiment.constants  import Sentiment, SENTIMENT_META

logger = logging.getLogger(__name__)

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
class AnalysisResult:
    text:           str
    sentiment:      str
    label:          str
    emoji:          str
    confidence:     float
    polarity_score: float
    is_confident:   bool
    all_scores:     dict[str, float]
    model_used:     str
    tokens_used:    int   = 0
    latency_ms:     float = 0.0
    is_fallback:    bool  = False


# ── Gemini system prompt ──────────────────────────────────────

def _build_prompt() -> str:
    examples_block = "\n".join(
        f'- "{k}": {v["description"]}\n'
        f'  Examples: {", ".join(repr(e) for e in v["examples"][:2])}'
        for k, v in SENTIMENT_META.items()
    )
    return (
        "You are a sentiment analysis engine for customer support messages.\n\n"
        "TASK: Classify the sentiment of the customer message into EXACTLY ONE "
        "of the following 4 classes and return a confidence score (0.0–1.0) for each.\n\n"
        f"CLASSES:\n{examples_block}\n\n"
        "OUTPUT FORMAT — return ONLY valid JSON, no markdown:\n"
        "{\n"
        '  "positive": 0.05,\n'
        '  "neutral": 0.10,\n'
        '  "negative": 0.15,\n'
        '  "very_negative": 0.70\n'
        "}\n\n"
        "RULES:\n"
        "1. Scores must sum to approximately 1.0.\n"
        "2. Assign the highest score to the ONE best-matching sentiment.\n"
        "3. Return ONLY the JSON object — no other text.\n"
        "4. Use exactly these keys: positive, neutral, negative, very_negative"
    )


# ── Core async function ───────────────────────────────────────

async def analyze_sentiment(
    text:      str,
    threshold: Optional[float] = None,
) -> AnalysisResult:
    """
    Analyse the sentiment of a text string using Gemini.
    Falls back to rule-based analysis on any failure.

    Args:
        text      : customer message or text to analyse
        threshold : confidence threshold (defaults to settings value)

    Returns:
        AnalysisResult — never raises.
    """
    _threshold = threshold if threshold is not None else settings.SENTIMENT_CONFIDENCE_THRESHOLD
    model_name = settings.SENTIMENT_MODEL
    start      = time.perf_counter()

    try:
        _ensure_configured()
    except RuntimeError:
        return _rule_based(text, model_name, start)

    def _blocking() -> tuple[str, int]:
        gen_config = genai.types.GenerationConfig(
            max_output_tokens=150,
            temperature=settings.SENTIMENT_TEMPERATURE,
            top_p=0.1,
            top_k=1,
        )
        model  = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=_build_prompt(),
            generation_config=gen_config,
        )
        result = model.generate_content(text)
        raw    = result.text or ""
        tokens = getattr(result.usage_metadata, "total_token_count", 0) or 0
        return raw.strip(), tokens

    try:
        raw_text, tokens_used = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(None, _blocking),
            timeout=float(settings.SENTIMENT_TIMEOUT),
        )
    except (asyncio.TimeoutError, Exception) as exc:
        logger.warning("Sentiment analysis error: %s — rule-based fallback", exc)
        return _rule_based(text, model_name, start)

    scores = _parse_scores(raw_text)
    if not scores:
        return _rule_based(text, model_name, start)

    # Normalise to sum = 1
    total  = sum(scores.values()) or 1.0
    scores = {k: round(v / total, 4) for k, v in scores.items()}

    top_sent  = max(scores, key=scores.get)
    top_score = scores[top_sent]
    latency   = round((time.perf_counter() - start) * 1000, 2)

    is_confident  = top_score >= _threshold
    final_sent    = top_sent if is_confident else Sentiment.NEUTRAL
    meta          = SENTIMENT_META[final_sent]
    polarity      = meta["polarity"]

    logger.info(
        "Sentiment | %s (%.3f) confident=%s latency=%.1fms",
        final_sent, top_score, is_confident, latency,
    )

    return AnalysisResult(
        text=text,
        sentiment=final_sent,
        label=meta["label"],
        emoji=meta["emoji"],
        confidence=top_score,
        polarity_score=polarity,
        is_confident=is_confident,
        all_scores=scores,
        model_used=model_name,
        tokens_used=tokens_used,
        latency_ms=latency,
        is_fallback=not is_confident,
    )


# ── Conversation aggregation ──────────────────────────────────

async def analyze_conversation_sentiment(
    messages: list[str],
) -> dict:
    """
    Analyse all messages and return aggregated conversation sentiment.

    Returns a dict with dominant_sentiment, average_polarity,
    distribution, and trend.
    """
    if not messages:
        return {
            "dominant_sentiment": Sentiment.NEUTRAL,
            "average_polarity":   0.0,
            "distribution":       {},
            "trend":              "stable",
            "results":            [],
        }

    # Analyse all messages concurrently
    tasks   = [analyze_sentiment(m) for m in messages]
    results = await asyncio.gather(*tasks)

    distribution: dict[str, int] = {s: 0 for s in Sentiment.all_values()}
    polarities: list[float] = []

    for r in results:
        distribution[r.sentiment] = distribution.get(r.sentiment, 0) + 1
        polarities.append(r.polarity_score)

    avg_polarity    = round(sum(polarities) / len(polarities), 3) if polarities else 0.0
    dominant_sent   = max(distribution, key=distribution.get)
    dominant_meta   = SENTIMENT_META[dominant_sent]

    # Trend: compare first half vs second half polarity
    mid   = len(polarities) // 2 or 1
    first = sum(polarities[:mid]) / mid
    last  = sum(polarities[mid:]) / max(len(polarities[mid:]), 1)

    if last - first > 0.3:
        trend = "improving"
    elif first - last > 0.3:
        trend = "declining"
    else:
        trend = "stable"

    return {
        "dominant_sentiment": dominant_sent,
        "dominant_label":     dominant_meta["label"],
        "dominant_emoji":     dominant_meta["emoji"],
        "average_polarity":   avg_polarity,
        "distribution":       {k: v for k, v in distribution.items() if v > 0},
        "trend":              trend,
        "results":            results,
    }


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
    valid  = set(Sentiment.all_values())
    scores = {}
    for key in valid:
        val = raw.get(key)
        try:
            scores[key] = float(val) if val is not None else 0.0
        except (TypeError, ValueError):
            scores[key] = 0.0
    return scores


# ── Keyword lexicon for rule-based fallback ───────────────────

_VERY_NEG = ["unacceptable", "terrible", "worst", "awful", "disgusting",
             "furious", "outrageous", "pathetic", "horrible", "hate",
             "cancel everything", "demand refund", "sue"]

_NEGATIVE  = ["disappointed", "frustrated", "not working", "broken", "failed",
              "unhappy", "issue", "problem", "slow", "annoying", "bad",
              "poor", "worst", "confused", "stuck", "error", "can't"]

_POSITIVE  = ["thank", "great", "excellent", "love", "perfect", "amazing",
              "wonderful", "helpful", "fast", "easy", "awesome", "pleased",
              "satisfied", "good", "appreciate", "works", "solved", "resolved"]


def _rule_based(text: str, model_name: str, start: float) -> AnalysisResult:
    lower   = text.lower()
    latency = round((time.perf_counter() - start) * 1000, 2)

    very_neg_n = sum(1 for w in _VERY_NEG  if w in lower)
    neg_n      = sum(1 for w in _NEGATIVE  if w in lower)
    pos_n      = sum(1 for w in _POSITIVE  if w in lower)

    if very_neg_n > 0:
        final = Sentiment.VERY_NEGATIVE
    elif neg_n > pos_n:
        final = Sentiment.NEGATIVE
    elif pos_n > neg_n:
        final = Sentiment.POSITIVE
    else:
        final = Sentiment.NEUTRAL

    meta     = SENTIMENT_META[final]
    conf     = 0.6 if any([very_neg_n, neg_n, pos_n]) else 0.3
    equal    = round(1 / 4, 4)
    scores   = {s: equal for s in Sentiment.all_values()}
    scores[final] = conf

    logger.info("Sentiment rule-based | %s latency=%.1fms", final, latency)

    return AnalysisResult(
        text=text,
        sentiment=final,
        label=meta["label"],
        emoji=meta["emoji"],
        confidence=conf,
        polarity_score=meta["polarity"],
        is_confident=conf >= settings.SENTIMENT_CONFIDENCE_THRESHOLD,
        all_scores=scores,
        model_used=f"{model_name}(rule-based)",
        tokens_used=0,
        latency_ms=latency,
        is_fallback=True,
    )
