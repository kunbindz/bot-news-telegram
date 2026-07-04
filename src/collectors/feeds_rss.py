"""Generic RSS collector for Hacker News, Dev.to, ProductHunt, GitHub Trending."""
import asyncio
import logging
import re
from calendar import timegm
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import List, Optional

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
    max_items: Optional[int] = None


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

        # Retry with exponential backoff
        last_error = None
        for attempt in range(3):
            try:
                async with session.get(source.url) as resp:
                    if resp.status == 429:
                        wait = 2 ** attempt
                        logger.warning(f"Feed {source.name}: rate limited (429), retry in {wait}s")
                        await asyncio.sleep(wait)
                        continue
                    resp.raise_for_status()
                    rss_text = await resp.text()
                break  # success
            except aiohttp.ClientError as e:
                last_error = e
                if attempt < 2:
                    wait = 1.5 * (attempt + 1)
                    logger.warning(f"Feed {source.name}: attempt {attempt+1} failed ({e}), retry in {wait}s")
                    await asyncio.sleep(wait)
        else:
            logger.error(f"Feed {source.name}: all retries failed: {last_error}")
            return []

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
            created = None
            if time_tuple:
                created = datetime.fromtimestamp(timegm(time_tuple), tz=timezone.utc)
                if created < cutoff:
                    continue

            title = getattr(entry, "title", "") or ""
            url = getattr(entry, "link", "") or ""
            author = getattr(entry, "author", "") or "unknown"

            raw = getattr(entry, "summary", "") or ""
            if not raw and getattr(entry, "content", None):
                raw = entry.content[0].get("value", "")
            content = _strip_html(raw)
            if len(content) > 4000:
                content = content[:4000] + "..."

            items.append(Item(
                source=f"{source.label}:{source.name}",
                title=title,
                content=content,
                url=url,
                author=author,
                published_at=created,
            ))
            if source.max_items and len(items) >= source.max_items:
                break

        logger.info(f"Feed {source.name}: collected {len(items)} candidates")
        return items

    async def collect(self) -> List[Item]:
        """Fetch all configured RSS feeds in parallel (semaphore-limited)."""
        headers = {"User-Agent": _USER_AGENT}
        timeout = aiohttp.ClientTimeout(total=15, connect=5)
        sem = asyncio.Semaphore(4)  # max 4 concurrent requests

        async def _fetch_with_limit(session: aiohttp.ClientSession,
                                     source: FeedSource) -> List[Item]:
            async with sem:
                await asyncio.sleep(self.request_delay)
                try:
                    return await self._fetch_feed(session, source)
                except Exception as e:
                    logger.error(f"Feed {source.name} error: {e}")
                    return []

        async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
            tasks = [_fetch_with_limit(session, s) for s in self.sources]
            results = await asyncio.gather(*tasks)

        all_items: List[Item] = []
        for items in results:
            all_items.extend(items)
        return all_items

    async def close(self):
        pass
