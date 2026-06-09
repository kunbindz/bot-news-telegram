"""Main pipeline: collect → keyword filter → dedupe → AI filter → send."""
import logging
from collections import Counter
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
        self.max_per_source = sched.get("max_per_source_per_cycle", 2)
        self.max_per_topic = sched.get("max_per_topic_per_cycle", 1)

    def _primary_topic(self, item: Item) -> str:
        tags = [t.strip().lower() for t in (item.summary_tags or []) if t and t.strip()]
        if tags:
            return tags[0]
        source_hint = item.short_source.lower()
        title_hint = f"{item.title} {item.content}".lower()
        for keyword in (
            "claude", "anthropic", "openai", "gpt", "gemini", "llama",
            "mistral", "deepseek", "qwen", "mcp", "agent", "cursor",
        ):
            if keyword in source_hint or keyword in title_hint:
                return keyword
        return (item.category or "other").lower()

    def _select_diverse_items(self, items: List[Item]) -> List[Item]:
        if len(items) <= self.max_send_per_cycle:
            return sorted(items, key=lambda x: x.score or 0, reverse=True)

        source_counts = Counter(it.source for it in items)
        topic_counts = Counter(self._primary_topic(it) for it in items)
        ranked = sorted(
            items,
            key=lambda it: (
                (it.score or 0)
                + min(0.6, 0.15 * max(0, 4 - source_counts[it.source]))
                + min(0.6, 0.2 * max(0, 3 - topic_counts[self._primary_topic(it)]))
            ),
            reverse=True,
        )

        selected: List[Item] = []
        selected_sources = Counter()
        selected_topics = Counter()

        for item in ranked:
            topic = self._primary_topic(item)
            if selected_sources[item.source] >= self.max_per_source:
                continue
            if selected_topics[topic] >= self.max_per_topic:
                continue
            selected.append(item)
            selected_sources[item.source] += 1
            selected_topics[topic] += 1
            if len(selected) >= self.max_send_per_cycle:
                return selected

        for item in ranked:
            if item in selected:
                continue
            if selected_sources[item.source] >= self.max_per_source:
                continue
            selected.append(item)
            selected_sources[item.source] += 1
            if len(selected) >= self.max_send_per_cycle:
                return selected

        for item in ranked:
            if item in selected:
                continue
            selected.append(item)
            if len(selected) >= self.max_send_per_cycle:
                return selected

        return selected

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

        # Step 5: cap per cycle with source/topic diversity
        if len(to_send) > self.max_send_per_cycle:
            before = len(to_send)
            to_send = self._select_diverse_items(to_send)
            logger.info(
                f"Diversity cap: selected {len(to_send)}/{before} "
                f"items (max={self.max_send_per_cycle}, "
                f"per_source={self.max_per_source}, per_topic={self.max_per_topic})"
            )

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
