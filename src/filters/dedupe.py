"""Deduplication filter using SQLite — batch optimized."""
import logging
from typing import List
from src.models import Item
from src import db

logger = logging.getLogger(__name__)


async def filter_seen(items: List[Item]) -> List[Item]:
    """Return only items not seen before. Uses single batch query."""
    if not items:
        return []
    # Build hash→item mapping
    hash_map = {}
    for it in items:
        h = db.make_hash(it.url, it.title)
        hash_map[h] = it

    # Single batch query instead of N individual queries
    seen_hashes = await db.filter_seen_hashes(list(hash_map.keys()))
    fresh = [it for h, it in hash_map.items() if h not in seen_hashes]

    logger.info(f"Dedupe: {len(fresh)}/{len(items)} are new")
    return fresh


async def record_items(items: List[Item], sent: bool = False):
    """Record items in DB after processing. Uses single batch transaction."""
    if not items:
        return
    items_data = []
    for it in items:
        items_data.append({
            "hash": db.make_hash(it.url, it.title),
            "source": it.source,
            "title": it.title,
            "url": it.url,
            "score": it.score,
            "category": it.category,
            "content": it.content,
            "author": it.author,
            "published_at": it.published_at,
            "vn_summary": it.vn_summary,
            "summary_what": it.summary_what,
            "summary_why": it.summary_why,
            "summary_action": it.summary_action,
            "summary_tags": it.summary_tags,
            "should_notify": it.should_notify,
        })
    await db.mark_seen_batch(items_data, sent=sent)
