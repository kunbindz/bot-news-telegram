"""Keyword-based pre-filter. Runs before AI to save credits."""
import logging
import re
from typing import List
from src.models import Item

logger = logging.getLogger(__name__)


class KeywordFilter:
    def __init__(self, whitelist: List[str], blacklist: List[str]):
        # Build regex patterns with word boundaries for accurate matching
        # e.g. "next.js" won't match "next.jscode"
        self.whitelist_patterns = [
            re.compile(r'(?<!\w)' + re.escape(w.lower()) + r'(?!\w)')
            for w in whitelist
        ]
        self.blacklist_patterns = [
            re.compile(r'(?<!\w)' + re.escape(w.lower()) + r'(?!\w)')
            for w in blacklist
        ]
        # Keep raw lists for logging
        self._whitelist_raw = [w.lower() for w in whitelist]
        self._blacklist_raw = [w.lower() for w in blacklist]

    def passes(self, item: Item) -> bool:
        """Return True if item should proceed to AI filter."""
        haystack = f"{item.title} {item.content}".lower()

        # Blacklist - reject immediately
        for i, pattern in enumerate(self.blacklist_patterns):
            if pattern.search(haystack):
                logger.debug(f"Blacklisted [{self._blacklist_raw[i]}]: {item.title[:50]}")
                return False

        # Whitelist - need at least 1 hit
        for pattern in self.whitelist_patterns:
            if pattern.search(haystack):
                return True

        return False

    def filter_batch(self, items: List[Item]) -> List[Item]:
        passed = [it for it in items if self.passes(it)]
        logger.info(f"Keyword filter: {len(passed)}/{len(items)} passed")
        return passed
