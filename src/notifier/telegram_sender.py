"""Telegram notification sender."""
import os
import asyncio
import logging
import html
from typing import List

from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import RetryAfter, TimedOut

from src.models import Item

logger = logging.getLogger(__name__)


CATEGORY_EMOJI = {
    "ai_news": "📰",
    "model_release": "🚀",
    "free_trial": "🎁",
    "deal_course": "🎓",
    "tool_tip": "💡",
    "quota_change": "📈",
    "other": "🔖",
}

SOURCE_EMOJI = {
    "reddit": "🔴",
    "hn": "🟠",
    "devto": "💜",
    "ph": "🟡",
    "github": "⚫",
    "twitter": "🐦",
    "hf": "🤗",
    "lobsters": "🦞",
    "simon": "✍️",
}


def _source_emoji(source: str) -> str:
    prefix = source.split(":")[0] if ":" in source else source
    return SOURCE_EMOJI.get(prefix, "📌")


def format_message(item: Item) -> str:
    """Format item as HTML for Telegram."""
    cat_emoji = CATEGORY_EMOJI.get(item.category or "other", "🔖")
    src_emoji = _source_emoji(item.source)
    category_label = (item.category or "other").replace("_", " ").title()

    title = html.escape(item.title or "")
    summary = html.escape(item.vn_summary or "")
    source = html.escape(item.short_source)
    url = item.url or ""

    parts = [
        f"{cat_emoji} <b>[{category_label}]</b>  {src_emoji} <i>{source}</i>",
        f"<b>{title}</b>",
        "",
        summary,
        "",
        f"📊 Score: <b>{item.score}/10</b>",
        f'🔗 <a href="{url}">Xem chi tiết</a>',
    ]
    return "\n".join(parts)


class TelegramSender:
    def __init__(self, batch_delay: float = 2.0):
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        if not token or not self.chat_id:
            raise RuntimeError(
                "TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set")
        self.bot = Bot(token=token)
        self.batch_delay = batch_delay

    async def send_item(self, item: Item) -> bool:
        text = format_message(item)
        for attempt in range(3):
            try:
                await self.bot.send_message(
                    chat_id=self.chat_id,
                    text=text,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=False,
                )
                return True
            except RetryAfter as e:
                logger.warning(f"Telegram rate limit, sleep {e.retry_after}s")
                await asyncio.sleep(e.retry_after + 1)
            except TimedOut:
                logger.warning("Telegram timeout, retrying")
                await asyncio.sleep(2)
            except Exception as e:
                logger.error(f"Telegram send error: {e}")
                return False
        return False

    async def send_batch(self, items: List[Item]) -> int:
        """Send all items, returns count sent successfully."""
        sent = 0
        # Sort high score first
        items_sorted = sorted(items, key=lambda x: x.score or 0, reverse=True)
        for it in items_sorted:
            ok = await self.send_item(it)
            if ok:
                sent += 1
            await asyncio.sleep(self.batch_delay)
        return sent

    async def send_text(self, text: str):
        """Send a plain text message (for /stats, errors, etc)."""
        try:
            await self.bot.send_message(
                chat_id=self.chat_id, text=text,
                parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"send_text error: {e}")
