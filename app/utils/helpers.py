"""
app/utils/helpers.py
─────────────────────
General-purpose utility functions shared across the application.
"""

import uuid
from datetime import datetime, timezone


def utc_now() -> datetime:
    """Return current UTC datetime (timezone-aware)."""
    return datetime.now(tz=timezone.utc)


def generate_conversation_id() -> str:
    """
    Generate a short, human-readable conversation ID.
    Format: CONV-YYYYMMDD-XXXXXXXX
    """
    date_str  = datetime.now(tz=timezone.utc).strftime("%Y%m%d")
    unique    = uuid.uuid4().hex[:8].upper()
    return f"CONV-{date_str}-{unique}"


def generate_ticket_id() -> str:
    """
    Generate a short, human-readable ticket ID.
    Format: TKT-YYYYMMDD-XXXXXXXX
    """
    date_str = datetime.now(tz=timezone.utc).strftime("%Y%m%d")
    unique   = uuid.uuid4().hex[:8].upper()
    return f"TKT-{date_str}-{unique}"
