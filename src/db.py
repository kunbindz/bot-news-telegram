"""SQLite database for deduplication and history."""
import aiosqlite
import hashlib
import os
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
                    sent: bool = False, score: int = None, category: str = None):
    """Record an item as seen."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT OR IGNORE INTO seen_items
               (hash, source, title, url, sent, score, category)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (item_hash, source, title, url, sent, score, category)
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
