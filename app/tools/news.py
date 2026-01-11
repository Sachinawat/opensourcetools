import logging
from datetime import datetime
from typing import List, Optional

import feedparser
import requests
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)


class NewsItem(BaseModel):
    title: str
    content: str
    published: Optional[str] = None
    source: Optional[str] = None


class NewsResult(BaseModel):
    count: int
    items: List[NewsItem] = Field(default_factory=list)
    source: str


def _clean_source(src) -> Optional[str]:
    if src is None:
        return None
    if isinstance(src, dict):
        # feedparser sometimes returns FeedParserDict with title/href
        return src.get("title") or src.get("href") or None
    return str(src)


def _trim(text: str, max_len: int = 240) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def _parse_entries(feed, limit: int) -> list[NewsItem]:
    items: list[NewsItem] = []
    for entry in feed.entries[:limit]:
        try:
            published = None
            if "published_parsed" in entry and entry.published_parsed:
                published = datetime(*entry.published_parsed[:6]).isoformat()
            items.append(
                NewsItem(
                    title=entry.title,
                    content=_trim(
                        getattr(entry, "summary", "") or getattr(entry, "description", "") or ""
                    ),
                    published=published,
                    source=None,  # hide source in output as per requirement
                )
            )
        except ValidationError as exc:
            logger.warning("Skipping malformed entry: %s", exc)
    return items


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


def _scrape_duckduckgo(topic: str, limit: int) -> list[NewsItem]:
    query = f"{topic} India news"
    url = "https://duckduckgo.com/html/"
    resp = requests.get(url, params={"q": query, "kl": "in-en"}, headers=HEADERS, timeout=10)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    results: list[NewsItem] = []
    for result in soup.select("div.result"):
        if len(results) >= limit:
            break
        title_el = result.select_one("a.result__a")
        snippet_el = result.select_one("a.result__snippet, div.result__snippet")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        snippet = snippet_el.get_text(" ", strip=True) if snippet_el else ""
        if not title:
            continue
        try:
            results.append(
                NewsItem(
                    title=title,
                    content=_trim(snippet or title),
                    source=None,  # suppress extra metadata
                )
            )
        except ValidationError as exc:
            logger.debug("Skipping scraped item: %s", exc)
            continue
    return results


def fetch_news(
    topic: str = "india",
    feed_url: str = "https://news.google.com/rss?hl=en-IN&gl=IN&ceid=IN:en",
    limit: int = 10,
) -> NewsResult:
    """
    Fetch latest Indian news. Tries DuckDuckGo (HTML scrape, no links) first, then RSS fallback.
    """
    limit = max(1, min(limit, 25))

    # First try DuckDuckGo HTML search (browser-like without headless dependencies)
    scraped_items = _scrape_duckduckgo(topic or "india", limit)
    if scraped_items:
        return NewsResult(count=len(scraped_items), items=scraped_items, source="duckduckgo")

    # Fallback to RSS
    url = feed_url
    if topic and topic.lower() != "india":
        url = f"https://news.google.com/rss/search?q={topic}+India&hl=en-IN&gl=IN&ceid=IN:en"

    feed = feedparser.parse(url)
    if feed.bozo:
        raise ValueError(f"Failed to parse feed: {feed.bozo_exception}")

    items = _parse_entries(feed, limit)
    return NewsResult(count=len(items), items=items, source=url)
