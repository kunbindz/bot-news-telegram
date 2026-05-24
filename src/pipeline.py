"""Main pipeline: collect → keyword filter → dedupe → AI filter → send."""
import logging
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from src.models import Item
from src.filters.keyword import KeywordFilter
from src.filters import dedupe
from src.filters.ai_classifier import MiMoClassifier
from src.notifier.telegram_sender import TelegramSender

if TYPE_CHECKING:
    from src.bot_commands import BotState

logger = logging.getLogger(__name__)


class Pipeline:
    def __init__(self, config: dict, state: Optional["BotState"] = None):
        self.config = config
        self.state = state
        self.keyword_filter = KeywordFilter(
            whitelist=config["keywords"]["whitelist"],
            blacklist=config["keywords"]["blacklist"],
        )
        self.min_score = config["ai_filter"]["min_score_to_notify"]
        self.ai_enabled = config["ai_filter"]["enabled"]
        sched = config["schedule"]
        self.max_send_per_cycle = sched.get("max_send_per_cycle", 5)
        self.quiet_start = sched.get("quiet_hours_start", 23)
        self.quiet_end = sched.get("quiet_hours_end", 7)
        self.quiet_min_score = sched.get("quiet_min_score", 9)
        if self.ai_enabled:
            self.classifier = MiMoClassifier(
                base_url=config["ai_filter"]["base_url"],
                model=config["ai_filter"]["model"],
                timeout=config["ai_filter"]["timeout_seconds"],
            )
        self.sender = TelegramSender(
            batch_delay=config["schedule"]["batch_send_delay_seconds"]
        )

    async def process(self, items: List[Item], source_name: str) -> dict:
        """Run full pipeline on a batch. Returns stats dict."""
        stats = {"collected": len(items), "keyword_passed": 0,
                 "new": 0, "ai_passed": 0, "sent": 0}

        if not items:
            return stats

        # Step 1: keyword pre-filter
        items = self.keyword_filter.filter_batch(items)
        stats["keyword_passed"] = len(items)
        if not items:
            return stats

        # Step 2: dedupe vs DB
        items = await dedupe.filter_seen(items)
        stats["new"] = len(items)
        if not items:
            return stats

        # Step 3: AI classify
        effective_min_score = (
            self.state.score_override if self.state and self.state.score_override
            else self.min_score
        )
        if self.ai_enabled:
            items = await self.classifier.classify_batch(items)
            to_send = [it for it in items
                       if it.should_notify and (it.score or 0) >= effective_min_score]
        else:
            to_send = items

        stats["ai_passed"] = len(to_send)

        # Step 4: quiet hours filter
        hour = datetime.now().hour
        in_quiet = (self.quiet_start <= hour or hour < self.quiet_end)
        if in_quiet:
            to_send = [it for it in to_send if (it.score or 0) >= self.quiet_min_score]
            if to_send:
                logger.info(f"Quiet hours ({hour}h): only sending {len(to_send)} urgent items (score>={self.quiet_min_score})")

        # Step 5: cap per cycle — keep top N by score
        if len(to_send) > self.max_send_per_cycle:
            to_send = sorted(to_send, key=lambda x: x.score or 0, reverse=True)[:self.max_send_per_cycle]
            logger.info(f"Capped to top {self.max_send_per_cycle} items this cycle")

        # Step 6: record all (so we don't re-process), then send filtered
        await dedupe.record_items(items, sent=False)

        # Skip send if paused
        if self.state and self.state.paused:
            logger.info(f"[{source_name}] Bot paused — skipping send of {len(to_send)} items")
            return stats

        if to_send:
            sent_count = await self.sender.send_batch(to_send)
            stats["sent"] = sent_count
            await dedupe.record_items(to_send[:sent_count], sent=True)

        logger.info(f"[{source_name}] stats: {stats}")
        return stats
