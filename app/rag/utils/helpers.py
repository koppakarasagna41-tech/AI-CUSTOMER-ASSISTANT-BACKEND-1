"""app/rag/utils/helpers.py — RAG-specific helper utilities."""

import uuid
from datetime import datetime, timezone


def _date() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y%m%d")


def generate_log_id() -> str:
    """RLOG-YYYYMMDD-XXXXXXXX"""
    return f"RLOG-{_date()}-{uuid.uuid4().hex[:8].upper()}"


def generate_rag_conversation_id() -> str:
    """RAG-YYYYMMDD-XXXXXXXX — for RAG-originated conversations."""
    return f"RAG-{_date()}-{uuid.uuid4().hex[:8].upper()}"


def truncate_preview(text: str, max_chars: int = 200) -> str:
    """Return a clean preview of chunk content."""
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0] + "…"
