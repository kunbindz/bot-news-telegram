"""Deduplication filter using SQLite."""
import logging
from typing import List
from src.models import Item
from src import db

logger = logging.getLogger(__name__)


async def filter_seen(items: List[Item]) -> List[Item]:
    """Return only items not seen before."""
    fresh = []
    for it in items:
        h = db.make_hash(it.url, it.title)
        if not await db.is_seen(h):
            fresh.append(it)
    logger.info(f"Dedupe: {len(fresh)}/{len(items)} are new")
    return fresh


async def record_items(items: List[Item], sent: bool = False):
    """Record items in DB after processing."""
    for it in items:
        h = db.make_hash(it.url, it.title)
        await db.mark_seen(h, it.source, it.title, it.url, sent,
                           it.score, it.category, it.content, it.author,
                           it.vn_summary, it.summary_what, it.summary_why,
                           it.summary_action, it.summary_tags,
                           it.should_notify)
