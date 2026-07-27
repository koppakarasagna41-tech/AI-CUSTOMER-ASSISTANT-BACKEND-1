"""
app/rag/confidence/scorer.py
──────────────────────────────
Calculates a composite confidence score for a RAG response.

Score is a weighted combination of:
  1. Top similarity score        (0–1)   weight 0.60
  2. Average similarity score    (0–1)   weight 0.20
  3. Chunk coverage bonus        (0–1)   weight 0.20
     — increases when more chunks were retrieved vs. top_k

Formula:
    score = (top_sim * 0.60) + (avg_sim * 0.20) + (coverage * 0.20)

A score ≥ RAG_CONFIDENCE_THRESHOLD  → return AI answer
A score <  RAG_CONFIDENCE_THRESHOLD  → escalate to human
"""

import logging
from dataclasses import dataclass

from app.config import settings
from app.rag.retrieval.similarity_search import RetrievedChunk

logger = logging.getLogger(__name__)


@dataclass
class ConfidenceResult:
    score:       float   # 0.0 – 1.0
    is_confident: bool   # True if score ≥ threshold
    top_sim:     float
    avg_sim:     float
    coverage:    float
    threshold:   float


def calculate_confidence(
    chunks:    list[RetrievedChunk],
    top_k:     int,
    threshold: float | None = None,
) -> ConfidenceResult:
    """
    Calculate a composite confidence score.

    Args:
        chunks    : retrieved chunks (already ranked by similarity)
        top_k     : configured top_k — used for coverage calculation
        threshold : override RAG_CONFIDENCE_THRESHOLD from settings

    Returns:
        ConfidenceResult
    """
    thresh = threshold if threshold is not None else settings.RAG_CONFIDENCE_THRESHOLD

    # Edge case: no chunks retrieved
    if not chunks:
        result = ConfidenceResult(
            score=0.0, is_confident=False,
            top_sim=0.0, avg_sim=0.0, coverage=0.0,
            threshold=thresh,
        )
        logger.info("Confidence: 0.0 — no chunks retrieved")
        return result

    similarities = [c.similarity for c in chunks]
    top_sim      = similarities[0]
    avg_sim      = sum(similarities) / len(similarities)
    # Coverage: ratio of retrieved chunks to requested top_k (capped at 1.0)
    coverage     = min(len(chunks) / max(top_k, 1), 1.0)

    score = round(
        (top_sim  * 0.60) +
        (avg_sim  * 0.20) +
        (coverage * 0.20),
        4,
    )

    is_confident = score >= thresh

    logger.info(
        "Confidence score=%.3f (top=%.3f avg=%.3f cov=%.3f) | threshold=%.2f | %s",
        score, top_sim, avg_sim, coverage, thresh,
        "PASS" if is_confident else "ESCALATE",
    )

    return ConfidenceResult(
        score=score,
        is_confident=is_confident,
        top_sim=top_sim,
        avg_sim=avg_sim,
        coverage=coverage,
        threshold=thresh,
    )
