"""
app/knowledge/parsers/url_loader.py
─────────────────────────────────────
Website content loader — fetches a URL and extracts readable text
using BeautifulSoup. Removes scripts, styles, nav, and footer noise.
"""

import logging
from urllib.parse import urlparse

import aiohttp
from bs4 import BeautifulSoup

from .base_parser import ParsedPage

logger = logging.getLogger(__name__)

# Tags whose content we strip entirely
_REMOVE_TAGS = {"script", "style", "nav", "footer", "header",
                "aside", "noscript", "iframe", "form"}

# Minimum page text length to be considered usable
_MIN_TEXT_LEN = 100


class UrlLoader:
    """Async website content loader."""

    def __init__(self, timeout: int = 20):
        self.timeout = timeout

    async def load(self, url: str) -> list[ParsedPage]:
        """
        Fetch `url` and return its main text as a single ParsedPage.
        Raises ValueError on fetch failure or empty content.
        """
        self._validate_url(url)
        html = await self._fetch(url)
        text = self._extract_text(html)

        if len(text) < _MIN_TEXT_LEN:
            raise ValueError(
                f"URL '{url}' returned too little readable text "
                f"({len(text)} chars). The page may be JavaScript-rendered."
            )

        logger.info("URL loaded: %d chars from %s", len(text), url)
        return [ParsedPage(text=text, page_number=0, metadata={"source_url": url})]

    # ── Internals ─────────────────────────────────────────────

    @staticmethod
    def _validate_url(url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"Only HTTP/HTTPS URLs are supported, got: {url!r}")

    async def _fetch(self, url: str) -> str:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (compatible; AI-SupportBot/1.0; "
                "+https://github.com/ai-customer-support)"
            )
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                    allow_redirects=True,
                ) as resp:
                    if resp.status != 200:
                        raise ValueError(
                            f"URL returned HTTP {resp.status}: {url}"
                        )
                    return await resp.text(errors="replace")
        except aiohttp.ClientError as exc:
            raise ValueError(f"Failed to fetch URL '{url}': {exc}") from exc

    @staticmethod
    def _extract_text(html: str) -> str:
        soup = BeautifulSoup(html, "lxml")

        # Remove noise tags
        for tag in soup.find_all(_REMOVE_TAGS):
            tag.decompose()

        # Try main content areas first
        for selector in ("main", "article", '[role="main"]', ".content", "#content"):
            container = soup.select_one(selector)
            if container:
                text = container.get_text(separator="\n", strip=True)
                if len(text) >= _MIN_TEXT_LEN:
                    return text

        # Fallback: full body
        body = soup.find("body") or soup
        text = body.get_text(separator="\n", strip=True)

        # Collapse excessive blank lines
        lines    = [line.strip() for line in text.splitlines()]
        cleaned  = "\n".join(
            line for line in lines if line
        )
        return cleaned
