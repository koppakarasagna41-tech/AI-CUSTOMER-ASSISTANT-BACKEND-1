"""
app/knowledge/utils/text_cleaner.py
─────────────────────────────────────
Text cleaning and normalisation utilities.

clean_text()  — main entry point: runs all cleaning steps in order
"""

import logging
import re
import unicodedata

logger = logging.getLogger(__name__)


def clean_text(text: str) -> str:
    """
    Full cleaning pipeline applied to every chunk before embedding.

    Steps:
      1. Unicode normalise (NFKC)
      2. Remove null bytes and control characters
      3. Replace Windows / weird line endings
      4. Collapse multiple blank lines (keep at most one)
      5. Remove invalid characters (non-printable, non-ASCII except accented)
      6. Collapse duplicate spaces
      7. Strip leading/trailing whitespace
    """
    if not text:
        return ""

    # 1. Normalise unicode (NFKC converts ligatures, half-width chars, etc.)
    text = unicodedata.normalize("NFKC", text)

    # 2. Remove null bytes and control characters except \n \t
    text = re.sub(r"[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]", " ", text)

    # 3. Normalise line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # 4. Remove lines that are just whitespace, collapse 3+ blank lines → 2
    text = re.sub(r"\n{3,}", "\n\n", text)

    # 5. Remove garbage non-printable runs (keep accented chars, CJK, etc.)
    text = re.sub(r"[^\S\n]+", " ", text)   # multiple spaces/tabs → single space

    # 6. Remove standalone symbols that add no value (bullet garbage)
    text = re.sub(r"(?<!\w)[•●▪▸►◦‣⁃](?!\w)", " ", text)

    # 7. Remove URL artifacts if text is not a URL source
    text = re.sub(r"https?://\S+", "[URL]", text)

    # 8. Strip
    text = text.strip()

    return text


def is_meaningful(text: str, min_chars: int = 50) -> bool:
    """
    Return True if the text is long enough and has real word content.
    Rejects chunks that are just numbers, symbols, or headers.
    """
    stripped = text.strip()
    if len(stripped) < min_chars:
        return False
    # Must have at least some alphabetic content
    alpha_ratio = sum(c.isalpha() for c in stripped) / max(len(stripped), 1)
    return alpha_ratio >= 0.25
