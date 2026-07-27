"""app/knowledge/utils/id_generator.py — ID generators for knowledge base entities."""

import uuid
from datetime import datetime, timezone


def _date() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y%m%d")


def generate_document_id() -> str:
    """KBD-YYYYMMDD-XXXXXXXX"""
    return f"KBD-{_date()}-{uuid.uuid4().hex[:8].upper()}"


def generate_chunk_id() -> str:
    """CHK-YYYYMMDD-XXXXXXXX"""
    return f"CHK-{_date()}-{uuid.uuid4().hex[:8].upper()}"
