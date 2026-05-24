"""Generic RSS collector for Hacker News, Dev.to, ProductHunt, GitHub Trending."""
import asyncio
import logging
import re
from calendar import timegm
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import List

import aiohttp
import feedparser

from src.models import Item

logger = logging.getLogger(__name__)

_USER_AGENT = "ai-deal-bot/1.0 (RSS reader for personal use)"


@dataclass
class FeedSource:
    name: str
    url: str
    label: str


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


class FeedsRSSCollector:
    def __init__(self, sources: List[dict], max_age_hours: int = 12,
                 request_delay: float = 1.0):
        self.sources = [FeedSource(**s) for s in sources]
        self.max_age_hours = max_age_hours
        self.request_delay = request_delay

    async def _fetch_feed(self, session: aiohttp.ClientSession,
                          source: FeedSource) -> List[Item]:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.max_age_hours)

        async with session.get(source.url) as resp:
            if resp.status == 429:
                logger.warning(f"Feed {source.name}: rate limited (429), skipping")
                return []
            resp.raise_for_status()
            rss_text = await resp.text()

        feed = feedparser.parse(rss_text)
        if not feed.entries:
            if feed.bozo:
                logger.warning(f"Feed {source.name}: malformed feed, skipping")
            else:
                logger.info(f"Feed {source.name}: no entries")
            return []

        items: List[Item] = []
        for entry in feed.entries:
            time_tuple = (getattr(entry, "published_parsed", None)
                          or getattr(entry, "updated_parsed", None))
            if time_tuple:
                created = datetime.fromtimestamp(timegm(time_tuple), tz=timezone.utc)
                if created < cutoff:
                    continue

            title = getattr(entry, "title", "") or ""
            url = getattr(entry, "link", "") or ""
            author = getattr(entry, "author", "") or "unknown"

            raw = getattr(entry, "summary", "") or ""
            content = _strip_html(raw)
            if len(content) > 1500:
                content = content[:1500] + "..."

            items.append(Item(
                source=f"{source.label}:{source.name}",
                title=title,
                content=content,
                url=url,
                author=author,
            ))

        logger.info(f"Feed {source.name}: collected {len(items)} candidates")
        return items

    async def collect(self) -> List[Item]:
        """Fetch all configured RSS feeds and return List[Item]."""
        headers = {"User-Agent": _USER_AGENT}
        all_items: List[Item] = []

        async with aiohttp.ClientSession(headers=headers) as session:
            for i, source in enumerate(self.sources):
                if i > 0:
                    await asyncio.sleep(self.request_delay)
                try:
                    items = await self._fetch_feed(session, source)
                    all_items.extend(items)
                except Exception as e:
                    logger.error(f"Feed {source.name} error: {e}")

        return all_items

    async def close(self):
        pass
