"""Reddit collector using public RSS feeds (no auth required)."""
import asyncio
import logging
import re
from calendar import timegm
from datetime import datetime, timezone, timedelta
from typing import List

import aiohttp
import feedparser

from src.models import Item

logger = logging.getLogger(__name__)

_USER_AGENT = "ai-deal-bot/1.0 (RSS reader for personal use)"
_RSS_URL = "https://www.reddit.com/r/{sub}/new/.rss?limit={limit}"


class RedditRSSCollector:
    def __init__(self, subreddits: List[str], posts_per_sub: int = 15,
                 max_age_hours: int = 6, request_delay: float = 1.5):
        self.subreddits = subreddits
        self.posts_per_sub = posts_per_sub
        self.max_age_hours = max_age_hours
        self.request_delay = request_delay

    async def _fetch_sub(self, session: aiohttp.ClientSession,
                         sub_name: str) -> List[Item]:
        url = _RSS_URL.format(sub=sub_name, limit=self.posts_per_sub)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.max_age_hours)

        async with session.get(url) as resp:
            if resp.status == 429:
                logger.warning(f"Reddit r/{sub_name}: rate limited (429), skipping")
                return []
            resp.raise_for_status()
            rss_text = await resp.text()

        feed = feedparser.parse(rss_text)

        if not feed.entries:
            if feed.bozo:
                logger.warning(f"Reddit r/{sub_name}: malformed feed, skipping")
            else:
                logger.info(f"Reddit r/{sub_name}: no entries returned")
            return []

        items: List[Item] = []
        for entry in feed.entries:
            if not getattr(entry, "published_parsed", None):
                continue
            created = datetime.fromtimestamp(
                timegm(entry.published_parsed), tz=timezone.utc
            )
            if created < cutoff:
                continue

            raw_author = getattr(entry, "author", "") or ""
            author = raw_author.lstrip("/u/").lstrip("u/") or "[deleted]"

            raw_summary = getattr(entry, "summary", "") or ""
            plain = re.sub(r"<[^>]+>", " ", raw_summary)
            plain = re.sub(r"\s+", " ", plain).strip()
            if len(plain) > 1500:
                plain = plain[:1500] + "..."

            items.append(Item(
                source=f"reddit:r/{sub_name}",
                title=entry.title,
                content=plain,
                url=entry.link,
                author=author,
                published_at=created,
            ))

        logger.info(f"Reddit r/{sub_name}: collected {len(items)} candidates")
        return items

    async def collect(self) -> List[Item]:
        """Fetch RSS from all configured subreddits and return List[Item]."""
        headers = {"User-Agent": _USER_AGENT}
        timeout = aiohttp.ClientTimeout(total=15, connect=5)
        all_items: List[Item] = []

        async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
            for i, sub_name in enumerate(self.subreddits):
                if i > 0:
                    await asyncio.sleep(self.request_delay)
                try:
                    items = await self._fetch_sub(session, sub_name)
                    all_items.extend(items)
                except Exception as e:
                    logger.error(f"Reddit r/{sub_name} error: {e}")

        return all_items

    async def close(self):
        pass
