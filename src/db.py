"""SQLite database for deduplication and history.

Uses a persistent connection singleton to avoid open/close overhead on every query.
"""
import asyncio
import aiosqlite
import hashlib
import json
import logging
import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Optional, Set

logger = logging.getLogger(__name__)

_default = Path(__file__).parent.parent / "db.sqlite"
DB_PATH = Path(os.getenv("DB_PATH", str(_default)))
# Đảm bảo thư mục chứa DB tồn tại (Railway volume mount /app/data chưa có sẵn)
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# ---------- Connection singleton ----------
_conn: Optional[aiosqlite.Connection] = None
_conn_lock = asyncio.Lock()


async def get_conn() -> aiosqlite.Connection:
    """Get or create the persistent DB connection."""
    global _conn
    if _conn is not None:
        return _conn
    async with _conn_lock:
        # Double-checked: another coroutine may have initialized while we waited.
        if _conn is None:
            conn = await aiosqlite.connect(DB_PATH)
            # WAL mode = concurrent reads + better write performance
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.execute("PRAGMA synchronous=NORMAL")
            _conn = conn
    return _conn


async def close_conn():
    """Close the persistent connection (call on shutdown)."""
    global _conn
    if _conn is not None:
        await _conn.close()
        _conn = None


# ---------- Schema ----------

async def init_db():
    """Initialize database tables."""
    conn = await get_conn()
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS seen_items (
            hash TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            title TEXT,
            url TEXT,
            seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            published_at TIMESTAMP,
            sent BOOLEAN DEFAULT 0,
            score INTEGER,
            category TEXT
        )
    """)
    await _ensure_seen_items_columns(conn)
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_seen_at ON seen_items(seen_at)
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS bot_state (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    await conn.commit()


async def _ensure_seen_items_columns(conn):
    """Add newer columns without requiring a destructive migration."""
    cursor = await conn.execute("PRAGMA table_info(seen_items)")
    existing = {row[1] for row in await cursor.fetchall()}
    columns = {
        "content": "TEXT",
        "author": "TEXT",
        "published_at": "TIMESTAMP",
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
            await conn.execute(f"ALTER TABLE seen_items ADD COLUMN {name} {definition}")


# ---------- Bot state ----------

async def load_bot_state() -> dict:
    """Load persisted bot state from DB."""
    conn = await get_conn()
    cursor = await conn.execute("SELECT key, value FROM bot_state")
    rows = await cursor.fetchall()
    return {row[0]: row[1] for row in rows}


async def save_bot_state(key: str, value: str):
    """Persist a single bot state key."""
    conn = await get_conn()
    await conn.execute(
        "INSERT OR REPLACE INTO bot_state (key, value) VALUES (?, ?)",
        (key, value)
    )
    await conn.commit()


# ---------- Hashing ----------

def make_hash(url: str, title: str = "") -> str:
    """Stable hash for an item based on URL + title."""
    raw = f"{url}|{title}".lower().strip()
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ---------- Single-item operations (kept for compatibility) ----------

async def is_seen(item_hash: str) -> bool:
    """Check if item already processed."""
    conn = await get_conn()
    cursor = await conn.execute(
        "SELECT 1 FROM seen_items WHERE hash = ?", (item_hash,)
    )
    return await cursor.fetchone() is not None


async def mark_seen(item_hash: str, source: str, title: str, url: str,
                    sent: bool = False, score: int = None, category: str = None,
                    content: str = None, author: str = None, published_at: Optional[datetime] = None,
                    vn_summary: str = None, summary_what: str = None,
                    summary_why: str = None, summary_action: str = None,
                    summary_tags=None, should_notify: bool = None):
    """Record an item as seen."""
    tags_json = json.dumps(summary_tags or [], ensure_ascii=False)
    pub_str = published_at.isoformat() if isinstance(published_at, datetime) else published_at
    conn = await get_conn()
    await conn.execute(
        """INSERT INTO seen_items
           (hash, source, title, url, sent, score, category, content, author, published_at,
            vn_summary, summary_what, summary_why, summary_action,
            summary_tags, should_notify)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(hash) DO UPDATE SET
               sent = CASE WHEN excluded.sent = 1 THEN 1 ELSE seen_items.sent END,
               score = COALESCE(excluded.score, seen_items.score),
               category = COALESCE(excluded.category, seen_items.category),
               content = COALESCE(excluded.content, seen_items.content),
               author = COALESCE(excluded.author, seen_items.author),
               published_at = COALESCE(excluded.published_at, seen_items.published_at),
               vn_summary = COALESCE(excluded.vn_summary, seen_items.vn_summary),
               summary_what = COALESCE(excluded.summary_what, seen_items.summary_what),
               summary_why = COALESCE(excluded.summary_why, seen_items.summary_why),
               summary_action = COALESCE(excluded.summary_action, seen_items.summary_action),
               summary_tags = COALESCE(excluded.summary_tags, seen_items.summary_tags),
               should_notify = COALESCE(excluded.should_notify, seen_items.should_notify)""",
        (
            item_hash, source, title, url, sent, score, category, content, author, pub_str,
            vn_summary, summary_what, summary_why, summary_action,
            tags_json, should_notify,
        )
    )
    await conn.commit()


# ---------- Batch operations (N+1 → 1 query) ----------

async def filter_seen_hashes(hashes: List[str]) -> Set[str]:
    """Return the set of hashes that are already seen. Single query instead of N."""
    if not hashes:
        return set()
    conn = await get_conn()
    # SQLite has a limit of ~999 variables; chunk if needed
    seen: Set[str] = set()
    chunk_size = 900
    for i in range(0, len(hashes), chunk_size):
        chunk = hashes[i:i + chunk_size]
        placeholders = ",".join("?" * len(chunk))
        cursor = await conn.execute(
            f"SELECT hash FROM seen_items WHERE hash IN ({placeholders})",
            chunk,
        )
        rows = await cursor.fetchall()
        seen.update(row[0] for row in rows)
    return seen


async def mark_seen_batch(items_data: List[dict], sent: bool = False):
    """Record multiple items in a single transaction.

    items_data: list of dicts with keys matching mark_seen params.
    """
    if not items_data:
        return
    conn = await get_conn()
    rows = []
    for d in items_data:
        tags_json = json.dumps(d.get("summary_tags") or [], ensure_ascii=False)
        pub = d.get("published_at")
        pub_str = pub.isoformat() if isinstance(pub, datetime) else pub
        rows.append((
            d["hash"], d["source"], d["title"], d["url"],
            sent, d.get("score"), d.get("category"),
            d.get("content"), d.get("author"), pub_str,
            d.get("vn_summary"), d.get("summary_what"),
            d.get("summary_why"), d.get("summary_action"),
            tags_json, d.get("should_notify"),
        ))
    await conn.executemany(
        """INSERT INTO seen_items
           (hash, source, title, url, sent, score, category, content, author, published_at,
            vn_summary, summary_what, summary_why, summary_action,
            summary_tags, should_notify)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(hash) DO UPDATE SET
               sent = CASE WHEN excluded.sent = 1 THEN 1 ELSE seen_items.sent END,
               score = COALESCE(excluded.score, seen_items.score),
               category = COALESCE(excluded.category, seen_items.category),
               content = COALESCE(excluded.content, seen_items.content),
               author = COALESCE(excluded.author, seen_items.author),
               published_at = COALESCE(excluded.published_at, seen_items.published_at),
               vn_summary = COALESCE(excluded.vn_summary, seen_items.vn_summary),
               summary_what = COALESCE(excluded.summary_what, seen_items.summary_what),
               summary_why = COALESCE(excluded.summary_why, seen_items.summary_why),
               summary_action = COALESCE(excluded.summary_action, seen_items.summary_action),
               summary_tags = COALESCE(excluded.summary_tags, seen_items.summary_tags),
               should_notify = COALESCE(excluded.should_notify, seen_items.should_notify)""",
        rows,
    )
    await conn.commit()
    logger.debug(f"Batch mark_seen: {len(rows)} items, sent={sent}")


# ---------- Queries ----------

async def cleanup_old(days: int = 30):
    """Delete records older than N days to keep DB small."""
    cutoff = datetime.now() - timedelta(days=days)
    conn = await get_conn()
    await conn.execute(
        "DELETE FROM seen_items WHERE seen_at < ?", (cutoff,)
    )
    await conn.commit()


async def get_top_unsent(hours: int = 24, limit: int = 5):
    """Get top scored unsent items from last N hours."""
    cutoff = datetime.now() - timedelta(hours=hours)
    conn = await get_conn()
    cursor = await conn.execute(
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
    conn = await get_conn()
    # Build dicts from cursor.description instead of mutating the shared
    # connection's row_factory (the connection is a singleton used concurrently
    # by scheduler jobs, command handlers and the health server).
    cursor = await conn.execute(
        f"""SELECT hash, source, title, url, seen_at, published_at, sent, score, category,
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
    cols = [c[0] for c in cursor.description]
    return [dict(zip(cols, row)) for row in rows]


async def mark_drafted(hashes):
    """Mark candidates as used in a generated draft."""
    if not hashes:
        return
    conn = await get_conn()
    await conn.executemany(
        "UPDATE seen_items SET drafted = 1, drafted_at = CURRENT_TIMESTAMP WHERE hash = ?",
        [(h,) for h in hashes],
    )
    await conn.commit()


async def get_stats(hours: int = 24):
    """Get stats for last N hours."""
    cutoff = datetime.now() - timedelta(hours=hours)
    conn = await get_conn()
    cursor = await conn.execute(
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
