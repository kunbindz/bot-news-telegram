"""Twitter/X collector using twscrape (no API key needed, uses real account)."""
import os
import logging
from datetime import datetime, timezone, timedelta
from typing import List

from src.models import Item

logger = logging.getLogger(__name__)


class TwitterScrapeCollector:
    def __init__(self, accounts: List[str], tweets_per_account: int = 10,
                 max_age_hours: int = 6):
        self.accounts = accounts
        self.tweets_per_account = tweets_per_account
        self.max_age_hours = max_age_hours
        self._api = None

    async def _get_api(self):
        if self._api is not None:
            return self._api

        from twscrape import API
        self._api = API()  # saves session to twscrape_accounts.db

        username = os.getenv("TWITTER_USERNAME")
        password = os.getenv("TWITTER_PASSWORD")
        email = os.getenv("TWITTER_EMAIL", "")

        if not username or not password:
            raise RuntimeError("TWITTER_USERNAME and TWITTER_PASSWORD must be set in .env")

        await self._api.pool.add_account(username, password, email, "")
        await self._api.pool.login_all()
        return self._api

    async def collect(self) -> List[Item]:
        from twscrape import gather

        api = await self._get_api()
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.max_age_hours)
        all_items: List[Item] = []

        for account in self.accounts:
            try:
                tweets = await gather(
                    api.search(f"from:{account}", limit=self.tweets_per_account)
                )
                items = []
                for tweet in tweets:
                    if tweet.date < cutoff:
                        continue
                    content = tweet.rawContent or ""
                    if len(content) > 1500:
                        content = content[:1500] + "..."
                    items.append(Item(
                        source=f"twitter:@{account}",
                        title=content[:120],
                        content=content,
                        url=f"https://x.com/{account}/status/{tweet.id}",
                        author=account,
                    ))
                all_items.extend(items)
                logger.info(f"Twitter @{account}: collected {len(items)} candidates")
            except Exception as e:
                logger.error(f"Twitter @{account} error: {e}")

        return all_items

    async def close(self):
        pass
