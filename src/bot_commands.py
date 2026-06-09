"""Telegram command handlers for interactive bot control."""
import html
import logging
import os
from dataclasses import dataclass
from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes

from src import db

logger = logging.getLogger(__name__)


@dataclass
class BotState:
    paused: bool = False
    score_override: Optional[int] = None  # None = use config default

    @classmethod
    async def load(cls) -> "BotState":
        data = await db.load_bot_state()
        state = cls()
        if "paused" in data:
            state.paused = data["paused"] == "1"
        if "score_override" in data:
            state.score_override = int(data["score_override"])
        return state

    async def save(self):
        await db.save_bot_state("paused", "1" if self.paused else "0")
        if self.score_override is not None:
            await db.save_bot_state("score_override", str(self.score_override))
        else:
            await db.save_bot_state("score_override", "")


SOURCE_EMOJI = {
    "reddit": "🔴", "hn": "🟠", "devto": "💜",
    "ph": "🟡", "github": "⚫", "twitter": "🐦",
    "anthropic": "🟣",
}


def _src_emoji(source: str) -> str:
    prefix = source.split(":")[0] if ":" in source else source
    return SOURCE_EMOJI.get(prefix, "📌")


class BotCommandHandlers:
    def __init__(self, state: BotState, config: dict):
        self.state = state
        self.config = config
        self._allowed_chat = str(os.getenv("TELEGRAM_CHAT_ID", ""))

    def _is_allowed(self, update: Update) -> bool:
        return str(update.effective_chat.id) == self._allowed_chat

    async def cmd_start(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._is_allowed(update):
            return
        text = (
            "🤖 <b>AI Deal Bot</b>\n\n"
            "Các lệnh:\n"
            "/status — trạng thái hiện tại\n"
            "/pause — tạm dừng gửi tin\n"
            "/resume — tiếp tục gửi tin\n"
            "/score N — đổi ngưỡng điểm (vd /score 8)\n"
            "/top — 5 tin điểm cao nhất 24h chưa gửi\n"
            "/stats — số liệu hôm nay"
        )
        await update.message.reply_html(text)

    async def cmd_status(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._is_allowed(update):
            return
        sched = self.config["schedule"]
        default_score = self.config["ai_filter"]["min_score_to_notify"]
        active_score = self.state.score_override or default_score

        status = "⏸ <b>PAUSED</b>" if self.state.paused else "▶️ <b>RUNNING</b>"
        score_note = f"(override, default={default_score})" if self.state.score_override else "(config default)"

        text = (
            f"{status}\n\n"
            f"📊 Min score: <b>{active_score}/10</b> {score_note}\n"
            f"🔔 Max/cycle: <b>{sched.get('max_send_per_cycle', 5)}</b>\n"
            f"🌙 Quiet hours: <b>{sched.get('quiet_hours_start', 23)}h–{sched.get('quiet_hours_end', 7)}h</b> "
            f"(urgent ≥{sched.get('quiet_min_score', 9)})\n"
            f"⏱ Reddit: mỗi {sched.get('reddit_interval_minutes', 15)} phút\n"
            f"⏱ Feeds: mỗi {sched.get('feeds_interval_minutes', 20)} phút"
        )
        await update.message.reply_html(text)

    async def cmd_pause(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._is_allowed(update):
            return
        if self.state.paused:
            await update.message.reply_text("Bot đã đang paused rồi.")
            return
        self.state.paused = True
        await self.state.save()
        await update.message.reply_text("⏸ Đã tạm dừng. Gửi /resume để bật lại.")

    async def cmd_resume(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._is_allowed(update):
            return
        if not self.state.paused:
            await update.message.reply_text("Bot đang chạy bình thường rồi.")
            return
        self.state.paused = False
        await self.state.save()
        await update.message.reply_text("▶️ Đã tiếp tục. Bot sẽ gửi tin ở cycle tiếp theo.")

    async def cmd_score(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._is_allowed(update):
            return
        args = ctx.args
        if not args or not args[0].isdigit():
            await update.message.reply_text("Dùng: /score N (ví dụ /score 8). N từ 1–10.")
            return
        n = int(args[0])
        if not 1 <= n <= 10:
            await update.message.reply_text("Score phải từ 1 đến 10.")
            return
        self.state.score_override = n
        await self.state.save()
        await update.message.reply_text(
            f"📊 Min score đã đổi thành <b>{n}/10</b>.\n"
            f"Gửi /score {self.config['ai_filter']['min_score_to_notify']} để về mặc định.",
            parse_mode="HTML"
        )

    async def cmd_top(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._is_allowed(update):
            return
        rows = await db.get_top_unsent(hours=24, limit=5)
        if not rows:
            await update.message.reply_text("Không có tin nào bị cắt trong 24h qua.")
            return
        lines = ["🏆 <b>Top tin chưa gửi (24h)</b>\n"]
        for i, (title, url, score, category, source) in enumerate(rows, 1):
            src_e = _src_emoji(source)
            cat = (category or "other").replace("_", " ").title()
            t = html.escape(title or "")[:80]
            lines.append(
                f"{i}. {src_e} <b>[{cat}]</b> ⭐{score}\n"
                f'   <a href="{url}">{t}</a>'
            )
        await update.message.reply_html("\n".join(lines), disable_web_page_preview=True)

    async def cmd_stats(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._is_allowed(update):
            return
        rows = await db.get_stats(hours=24)
        if not rows:
            await update.message.reply_text("Chưa có dữ liệu trong 24h qua.")
            return
        total_seen = sum(r[0] for r in rows)
        total_sent = sum(r[1] for r in rows)
        lines = ["📈 <b>Thống kê 24h</b>\n"]
        for total, sent, source in sorted(rows, key=lambda x: -x[0]):
            e = _src_emoji(source)
            src_label = html.escape(source.split(":")[-1] if ":" in source else source)
            lines.append(f"{e} {src_label}: <b>{sent}</b> gửi / {total} xử lý")
        lines.append(f"\n✅ Tổng: <b>{total_sent}</b> gửi / {total_seen} xử lý")
        await update.message.reply_html("\n".join(lines))
