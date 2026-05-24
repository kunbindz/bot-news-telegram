"""Twitter collector via Nitter RSS feeds (no API key needed)."""
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import List
from email.utils import parsedate_to_datetime

import aiohttp
import feedparser

from src.models import Item

logger = logging.getLogger(__name__)


class TwitterNitterCollector:
    def __init__(self, accounts: List[str], nitter_instances: List[str],
                 max_age_hours: int = 12):
        self.accounts = accounts
        self.instances = nitter_instances
        self.max_age_hours = max_age_hours
        # Cache the working instance to avoid re-probing every cycle
        self._working_instance = None

    async def _fetch_with_fallback(self, session: aiohttp.ClientSession,
                                    account: str) -> str:
        """Try each Nitter instance until one returns RSS."""
        # Try cached first
        candidates = []
        if self._working_instance:
            candidates.append(self._working_instance)
        for inst in self.instances:
            if inst != self._working_instance:
                candidates.append(inst)

        for instance in candidates:
            url = f"{instance}/{account}/rss"
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(
                        total=15)) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        if "<rss" in text or "<feed" in text:
                            self._working_instance = instance
                            return text
                        logger.warning(
                            f"Nitter {instance}/{account}: non-RSS response")
                    else:
                        logger.warning(
                            f"Nitter {instance}/{account}: HTTP {resp.status}")
            except Exception as e:
                logger.warning(f"Nitter {instance}/{account} failed: {e}")
                continue
        return ""

    async def collect(self) -> List[Item]:
        items: List[Item] = []
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.max_age_hours)

        async with aiohttp.ClientSession() as session:
            tasks = [self._fetch_with_fallback(session, acc)
                     for acc in self.accounts]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        for account, rss_text in zip(self.accounts, results):
            if isinstance(rss_text, Exception) or not rss_text:
                continue
            try:
                feed = feedparser.parse(rss_text)
                for entry in feed.entries[:10]:
                    # Parse published date
                    pub = None
                    if hasattr(entry, "published"):
                        try:
                            pub = parsedate_to_datetime(entry.published)
                            if pub.tzinfo is None:
                                pub = pub.replace(tzinfo=timezone.utc)
                        except Exception:
                            pass
                    if pub and pub < cutoff:
                        continue

                    # Skip RT
                    title = entry.get("title", "")
                    if title.startswith("RT by"):
                        continue

                    content = entry.get("summary", "") or entry.get(
                        "description", "")
                    # Strip basic HTML
                    import re
                    content = re.sub(r"<[^>]+>", " ", content)
                    content = re.sub(r"\s+", " ", content).strip()
                    if len(content) > 800:
                        content = content[:800] + "..."

                    items.append(Item(
                        source=f"twitter:@{account}",
                        title=title[:200],
                        content=content,
                        url=entry.get("link", ""),
                        author=f"@{account}",
                    ))
                logger.info(f"Twitter @{account}: parsed feed")
            except Exception as e:
                logger.error(f"Twitter @{account} parse error: {e}")

        return items
