"""
app/knowledge/parsers/txt_parser.py
─────────────────────────────────────
Plain text, Markdown, and JSON FAQ parser.
- TXT / MD: read as-is.
- JSON: expects {"faqs": [{"question": "...", "answer": "..."}]}
  or a flat list of strings, or any JSON serialised to text.
"""

import json
import logging
from pathlib import Path

import chardet

from .base_parser import BaseParser, ParsedPage

logger = logging.getLogger(__name__)


class TxtParser(BaseParser):

    def parse(self, file_path: str) -> list[ParsedPage]:
        path = Path(file_path)
        if not path.exists():
            raise ValueError(f"File not found: {file_path}")

        suffix = path.suffix.lower().lstrip(".")

        try:
            raw   = path.read_bytes()
            enc   = chardet.detect(raw).get("encoding") or "utf-8"
            text  = raw.decode(enc, errors="replace")
        except Exception as exc:
            raise ValueError(f"Failed to read '{path.name}': {exc}") from exc

        if suffix == "json":
            text = self._parse_json(text, path.name)

        if not text.strip():
            logger.warning("TxtParser: empty content in %s", path.name)
            return []

        return [ParsedPage(text=text, page_number=0)]

    # ── JSON FAQ handling ────────────────────────────────────

    @staticmethod
    def _parse_json(raw: str, filename: str) -> str:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return raw   # treat as plain text if not valid JSON

        lines: list[str] = []

        # FAQ format: {"faqs": [{question, answer}, ...]}
        if isinstance(data, dict):
            faqs = data.get("faqs") or data.get("items") or []
            if faqs and isinstance(faqs, list):
                for item in faqs:
                    if isinstance(item, dict):
                        q = item.get("question") or item.get("q") or ""
                        a = item.get("answer")   or item.get("a") or ""
                        if q:
                            lines.append(f"Q: {q}")
                        if a:
                            lines.append(f"A: {a}")
                        lines.append("")
                return "\n".join(lines) if lines else json.dumps(data, indent=2)
            # Generic dict — serialise nicely
            return json.dumps(data, indent=2)

        # List of strings or dicts
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    q = item.get("question") or item.get("q") or ""
                    a = item.get("answer")   or item.get("a") or ""
                    if q:
                        lines.append(f"Q: {q}")
                    if a:
                        lines.append(f"A: {a}")
                    lines.append("")
                elif isinstance(item, str):
                    lines.append(item)
            return "\n".join(lines) if lines else raw

        return raw
