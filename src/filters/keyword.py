"""Keyword-based pre-filter. Runs before AI to save credits."""
import logging
from typing import List
from src.models import Item

logger = logging.getLogger(__name__)


class KeywordFilter:
    def __init__(self, whitelist: List[str], blacklist: List[str]):
        self.whitelist = [w.lower() for w in whitelist]
        self.blacklist = [w.lower() for w in blacklist]

    def passes(self, item: Item) -> bool:
        """Return True if item should proceed to AI filter."""
        haystack = f"{item.title} {item.content}".lower()

        # Blacklist - reject immediately
        for word in self.blacklist:
            if word in haystack:
                logger.debug(f"Blacklisted [{word}]: {item.title[:50]}")
                return False

        # Whitelist - need at least 1 hit
        for word in self.whitelist:
            if word in haystack:
                return True

        return False

    def filter_batch(self, items: List[Item]) -> List[Item]:
        passed = [it for it in items if self.passes(it)]
        logger.info(f"Keyword filter: {len(passed)}/{len(items)} passed")
        return passed
