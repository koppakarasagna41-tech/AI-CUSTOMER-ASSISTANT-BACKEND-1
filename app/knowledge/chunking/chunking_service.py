"""
app/knowledge/chunking/chunking_service.py
─────────────────────────────────────────────
Semantic chunking service.

Strategy: sliding-window character-based chunking that respects
sentence and paragraph boundaries.

chunk_document()   — splits a list of ParsedPages into TextChunk objects
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from app.config import settings
from app.knowledge.parsers.base_parser import ParsedPage
from app.knowledge.utils.text_cleaner import clean_text, is_meaningful
from app.knowledge.utils.id_generator import generate_chunk_id

logger = logging.getLogger(__name__)


@dataclass
class TextChunk:
    """
    An in-memory chunk before it is persisted to MongoDB or ChromaDB.
    """
    chunk_id:       str
    document_id:    str
    chunk_index:    int
    content:        str
    char_count:     int

    # Metadata for ChromaDB and MongoDB
    filename:       str
    original_name:  str
    source:         str
    category:       str
    page_number:    Optional[int] = None
    uploaded_by:    str           = ""
    uploaded_at:    Optional[datetime] = None
    metadata:       dict          = field(default_factory=dict)


def chunk_document(
    pages:         list[ParsedPage],
    document_id:   str,
    filename:      str,
    original_name: str,
    source:        str,
    category:      str,
    uploaded_by:   str,
    uploaded_at:   Optional[datetime] = None,
    chunk_size:    int = 0,
    chunk_overlap: int = 0,
) -> list[TextChunk]:
    """
    Split all pages of a document into clean, overlapping text chunks.

    Args:
        pages         : ParsedPage list from any parser
        document_id   : parent document identifier
        filename      : stored filename
        original_name : original uploaded filename
        source        : file path or URL
        category      : user-supplied category
        uploaded_by   : user ID of uploader
        uploaded_at   : upload timestamp
        chunk_size    : chars per chunk (defaults to settings value)
        chunk_overlap : overlap chars (defaults to settings value)

    Returns:
        List of TextChunk objects (already cleaned, filtered by minimum size)
    """
    c_size    = chunk_size    or settings.KB_CHUNK_SIZE
    c_overlap = chunk_overlap or settings.KB_CHUNK_OVERLAP
    min_size  = settings.KB_MIN_CHUNK_SIZE

    chunks:      list[TextChunk] = []
    chunk_index: int             = 0

    for page in pages:
        cleaned = clean_text(page.text)
        if not cleaned:
            continue

        # Split into raw character windows
        raw_windows = _sliding_window(cleaned, c_size, c_overlap)

        for window in raw_windows:
            # Re-clean the window (handles edge artifacts from splitting)
            content = clean_text(window)
            if not is_meaningful(content, min_chars=min_size):
                continue

            chunks.append(TextChunk(
                chunk_id=generate_chunk_id(),
                document_id=document_id,
                chunk_index=chunk_index,
                content=content,
                char_count=len(content),
                filename=filename,
                original_name=original_name,
                source=source,
                category=category,
                page_number=page.page_number if page.page_number else None,
                uploaded_by=uploaded_by,
                uploaded_at=uploaded_at,
                metadata=page.metadata,
            ))
            chunk_index += 1

    logger.info(
        "Chunked document %s → %d chunks (pages=%d chunk_size=%d overlap=%d)",
        document_id, len(chunks), len(pages), c_size, c_overlap,
    )
    return chunks


# ── Internal helpers ──────────────────────────────────────────

def _sliding_window(text: str, size: int, overlap: int) -> list[str]:
    """
    Split text into overlapping windows.
    Tries to split at sentence boundaries ('. ', '\\n') rather than
    mid-word to preserve semantic coherence.
    """
    if len(text) <= size:
        return [text]

    windows: list[str] = []
    start   = 0

    while start < len(text):
        end = min(start + size, len(text))

        # Try to find a natural break point near `end`
        if end < len(text):
            # Look back up to 120 chars for a sentence end or paragraph break
            search_start = max(end - 120, start + size // 2)
            best_break   = _find_break(text, search_start, end)
            if best_break:
                end = best_break

        window = text[start:end].strip()
        if window:
            windows.append(window)

        # Next start is end minus overlap, snapped to a word boundary
        next_start = end - overlap
        if next_start <= start:
            next_start = start + 1   # prevent infinite loop on tiny texts
        start = next_start

    return windows


def _find_break(text: str, search_start: int, end: int) -> Optional[int]:
    """
    Find the last sentence / paragraph break between search_start and end.
    Returns the index just after the break character, or None.
    """
    # Priority: paragraph break → sentence end → comma
    for pattern in (r"\n\n", r"\. ", r"\? ", r"! ", r"\n", r", "):
        for m in re.finditer(pattern, text[search_start:end]):
            return search_start + m.end()
    return None
