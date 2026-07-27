"""
app/knowledge/parsers/csv_parser.py
─────────────────────────────────────
CSV parser — converts each row to a natural-language sentence.
Handles encoding detection automatically via chardet.
"""

import csv
import io
import logging
from pathlib import Path

import chardet

from .base_parser import BaseParser, ParsedPage

logger = logging.getLogger(__name__)


class CsvParser(BaseParser):

    def parse(self, file_path: str) -> list[ParsedPage]:
        path = Path(file_path)
        if not path.exists():
            raise ValueError(f"File not found: {file_path}")

        try:
            raw = path.read_bytes()
            enc = chardet.detect(raw).get("encoding") or "utf-8"
            text = raw.decode(enc, errors="replace")
        except Exception as exc:
            raise ValueError(f"Failed to read CSV '{path.name}': {exc}") from exc

        try:
            reader  = csv.DictReader(io.StringIO(text))
            headers = reader.fieldnames or []
            lines:  list[str] = []

            for i, row in enumerate(reader):
                # Convert each row to "Header: value, Header: value, ..." format
                parts = [
                    f"{k.strip()}: {v.strip()}"
                    for k, v in row.items()
                    if v and v.strip()
                ]
                if parts:
                    lines.append(", ".join(parts))

            full_text = "\n".join(lines)
            if not full_text.strip():
                logger.warning("CSV produced no text: %s", path.name)
                return []

            logger.info("CSV parsed: %d rows from %s", len(lines), path.name)
            return [ParsedPage(
                text=full_text,
                page_number=0,
                metadata={"headers": headers, "row_count": len(lines)},
            )]

        except Exception as exc:
            logger.error("CSV parse error: %s | %s", path.name, exc)
            raise ValueError(f"Failed to parse CSV '{path.name}': {exc}") from exc
