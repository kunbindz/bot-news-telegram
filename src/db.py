"""SQLite database for deduplication and history."""
import aiosqlite
import hashlib
import os
import json
from pathlib import Path
from datetime import datetime, timedelta

_default = Path(__file__).parent.parent / "db.sqlite"
DB_PATH = Path(os.getenv("DB_PATH", str(_default)))


async def init_db():
    """Initialize database tables."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS seen_items (
                hash TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                title TEXT,
                url TEXT,
                seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                sent BOOLEAN DEFAULT 0,
                score INTEGER,
                category TEXT
            )
        """)
        await _ensure_seen_items_columns(db)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_seen_at ON seen_items(seen_at)
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bot_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        await db.commit()


async def _ensure_seen_items_columns(db):
    """Add newer columns without requiring a destructive migration."""
    cursor = await db.execute("PRAGMA table_info(seen_items)")
    existing = {row[1] for row in await cursor.fetchall()}
    columns = {
        "content": "TEXT",
        "author": "TEXT",
        "vn_summary": "TEXT",
        "summary_what": "TEXT",
        "summary_why": "TEXT",
        "summary_action": "TEXT",
        "summary_tags": "TEXT",
        "should_notify": "BOOLEAN",
        "drafted": "BOOLEAN DEFAULT 0",
        "drafted_at": "TIMESTAMP",
    }
    for name, definition in columns.items():
        if name not in existing:
            await db.execute(f"ALTER TABLE seen_items ADD COLUMN {name} {definition}")


async def load_bot_state() -> dict:
    """Load persisted bot state from DB."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT key, value FROM bot_state")
        rows = await cursor.fetchall()
        return {row[0]: row[1] for row in rows}


async def save_bot_state(key: str, value: str):
    """Persist a single bot state key."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO bot_state (key, value) VALUES (?, ?)",
            (key, value)
        )
        await db.commit()


def make_hash(url: str, title: str = "") -> str:
    """Stable hash for an item based on URL + title."""
    raw = f"{url}|{title}".lower().strip()
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


async def is_seen(item_hash: str) -> bool:
    """Check if item already processed."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT 1 FROM seen_items WHERE hash = ?", (item_hash,)
        )
        return await cursor.fetchone() is not None


async def mark_seen(item_hash: str, source: str, title: str, url: str,
                    sent: bool = False, score: int = None, category: str = None,
                    content: str = None, author: str = None,
                    vn_summary: str = None, summary_what: str = None,
                    summary_why: str = None, summary_action: str = None,
                    summary_tags=None, should_notify: bool = None):
    """Record an item as seen."""
    tags_json = json.dumps(summary_tags or [], ensure_ascii=False)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO seen_items
               (hash, source, title, url, sent, score, category, content, author,
                vn_summary, summary_what, summary_why, summary_action,
                summary_tags, should_notify)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(hash) DO UPDATE SET
                   sent = CASE WHEN excluded.sent = 1 THEN 1 ELSE seen_items.sent END,
                   score = COALESCE(excluded.score, seen_items.score),
                   category = COALESCE(excluded.category, seen_items.category),
                   content = COALESCE(excluded.content, seen_items.content),
                   author = COALESCE(excluded.author, seen_items.author),
                   vn_summary = COALESCE(excluded.vn_summary, seen_items.vn_summary),
                   summary_what = COALESCE(excluded.summary_what, seen_items.summary_what),
                   summary_why = COALESCE(excluded.summary_why, seen_items.summary_why),
                   summary_action = COALESCE(excluded.summary_action, seen_items.summary_action),
                   summary_tags = COALESCE(excluded.summary_tags, seen_items.summary_tags),
                   should_notify = COALESCE(excluded.should_notify, seen_items.should_notify)""",
            (
                item_hash, source, title, url, sent, score, category, content, author,
                vn_summary, summary_what, summary_why, summary_action,
                tags_json, should_notify,
            )
        )
        await db.commit()


async def cleanup_old(days: int = 30):
    """Delete records older than N days to keep DB small."""
    cutoff = datetime.now() - timedelta(days=days)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM seen_items WHERE seen_at < ?", (cutoff,)
        )
        await db.commit()


async def get_top_unsent(hours: int = 24, limit: int = 5):
    """Get top scored unsent items from last N hours."""
    cutoff = datetime.now() - timedelta(hours=hours)
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """SELECT title, url, score, category, source
               FROM seen_items
               WHERE sent = 0 AND score IS NOT NULL AND seen_at >= ?
               ORDER BY score DESC LIMIT ?""",
            (cutoff, limit)
        )
        return await cursor.fetchall()


async def get_top_candidates(hours: int = 24, limit: int = 5,
                             min_score: int = 8, include_drafted: bool = False):
    """Get full scored candidates for draft generation."""
    cutoff = datetime.now() - timedelta(hours=hours)
    drafted_filter = "" if include_drafted else "AND COALESCE(drafted, 0) = 0"
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            f"""SELECT hash, source, title, url, seen_at, sent, score, category,
                      content, author, vn_summary, summary_what, summary_why,
                      summary_action, summary_tags, should_notify
               FROM seen_items
               WHERE score IS NOT NULL
                 AND score >= ?
                 AND seen_at >= ?
                 {drafted_filter}
               ORDER BY score DESC, seen_at DESC
               LIMIT ?""",
            (min_score, cutoff, limit)
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def mark_drafted(hashes):
    """Mark candidates as used in a generated draft."""
    if not hashes:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executemany(
            "UPDATE seen_items SET drafted = 1, drafted_at = CURRENT_TIMESTAMP WHERE hash = ?",
            [(h,) for h in hashes],
        )
        await db.commit()


async def get_stats(hours: int = 24):
    """Get stats for last N hours."""
    cutoff = datetime.now() - timedelta(hours=hours)
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """SELECT
                COUNT(*) as total,
                SUM(CASE WHEN sent = 1 THEN 1 ELSE 0 END) as sent,
                source
               FROM seen_items
               WHERE seen_at >= ?
               GROUP BY source""",
            (cutoff,)
        )
        rows = await cursor.fetchall()
        return rows
