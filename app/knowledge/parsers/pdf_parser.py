"""
app/knowledge/parsers/pdf_parser.py
─────────────────────────────────────
PDF text extraction using PyPDF2.
Extracts text page-by-page, preserving page numbers for metadata.
"""

import logging
from pathlib import Path

from .base_parser import BaseParser, ParsedPage

logger = logging.getLogger(__name__)


class PdfParser(BaseParser):

    def parse(self, file_path: str) -> list[ParsedPage]:
        try:
            import PyPDF2
        except ImportError:
            raise ImportError("PyPDF2 is required for PDF parsing: pip install pypdf2")

        path = Path(file_path)
        if not path.exists():
            raise ValueError(f"File not found: {file_path}")

        pages: list[ParsedPage] = []
        try:
            with open(path, "rb") as fh:
                reader = PyPDF2.PdfReader(fh)
                total  = len(reader.pages)
                logger.info("PDF has %d pages: %s", total, path.name)

                for i, page in enumerate(reader.pages):
                    try:
                        text = page.extract_text() or ""
                    except Exception as exc:
                        logger.warning("Failed to extract page %d: %s", i, exc)
                        text = ""

                    if text.strip():
                        pages.append(ParsedPage(
                            text=text,
                            page_number=i + 1,
                            metadata={"total_pages": total},
                        ))

        except Exception as exc:
            logger.error("PDF parse error: %s | %s", path.name, exc)
            raise ValueError(f"Failed to parse PDF '{path.name}': {exc}") from exc

        logger.info("PDF parsed: %d non-empty pages from %s", len(pages), path.name)
        return pages
