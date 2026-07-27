"""
app/knowledge/parsers/base_parser.py
──────────────────────────────────────
Base class and shared data types for all document parsers.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ParsedPage:
    """
    Represents one logical 'page' of extracted text.
    For non-paginated documents (TXT, CSV, URL), page_number=0.
    """
    text:        str
    page_number: int  = 0
    metadata:    dict = field(default_factory=dict)


class BaseParser:
    """
    Abstract base for all parsers.
    Subclasses must implement parse().
    """

    def parse(self, file_path: str) -> list[ParsedPage]:
        """
        Parse a file and return a list of ParsedPage objects.
        Raises ValueError on unsupported file or parse failure.
        """
        raise NotImplementedError
