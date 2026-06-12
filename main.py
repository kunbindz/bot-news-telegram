"""AI Deal Bot - main entry point.

Usage:
  python main.py            # run scheduler (production)
  python main.py --once     # run one cycle and exit (for testing)
  python main.py --test-telegram  # send a test message to verify Telegram setup
"""
import asyncio
import argparse
import logging
import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from telegram.ext import ApplicationBuilder, CommandHandler

from src import db
from src.collectors.reddit_rss import RedditRSSCollector
from src.collectors.feeds_rss import FeedsRSSCollector
from src.collectors.twitter_scrape import TwitterScrapeCollector
from src.pipeline import Pipeline
from src.notifier.telegram_sender import TelegramSender
from src.bot_commands import BotState, BotCommandHandlers


# ---------- Logging ----------
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "bot.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
# Silence noisy libs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)

logger = logging.getLogger("main")


def load_config() -> dict:
    with open(Path(__file__).parent / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------- Jobs ----------
async def reddit_job(pipeline: Pipeline, collector: RedditRSSCollector):
    logger.info("=== Reddit cycle start ===")
    try:
        items = await collector.collect()
        await pipeline.process(items, "reddit")
    except Exception as e:
        logger.exception(f"Reddit job error: {e}")


async def twitter_job(pipeline: Pipeline, collector: TwitterScrapeCollector):
    logger.info("=== Twitter cycle start ===")
    try:
        items = await collector.collect()
        await pipeline.process(items, "twitter")
    except Exception as e:
        logger.exception(f"Twitter job error: {e}")


async def feeds_job(pipeline: Pipeline, collector: FeedsRSSCollector):
    logger.info("=== Feeds cycle start ===")
    try:
        items = await collector.collect()
        await pipeline.process(items, "feeds")
    except Exception as e:
        logger.exception(f"Feeds job error: {e}")


async def cleanup_job():
    logger.info("=== DB cleanup ===")
    await db.cleanup_old(days=30)


# ---------- Modes ----------
async def run_once(config: dict):
    """Run all collectors once and exit."""
    await db.init_db()
    pipeline = Pipeline(config)
    reddit_coll = RedditRSSCollector(
        subreddits=config["reddit"]["subreddits"],
        posts_per_sub=config["reddit"]["posts_per_sub"],
        max_age_hours=config["reddit"]["max_age_hours"],
        request_delay=config["reddit"].get("request_delay_seconds", 1.5),
    )
    feeds_coll = FeedsRSSCollector(
        sources=config["feeds"]["sources"],
        max_age_hours=config["feeds"]["max_age_hours"],
        request_delay=config["feeds"].get("request_delay_seconds", 1.0),
    )
    twitter_coll = TwitterScrapeCollector(
        accounts=config["twitter"]["accounts"],
        tweets_per_account=config["twitter"].get("tweets_per_account", 10),
        max_age_hours=config["twitter"].get("max_age_hours", 6),
    )
    try:
        await reddit_job(pipeline, reddit_coll)
        await feeds_job(pipeline, feeds_coll)
        if config["twitter"].get("enabled", False):
            await twitter_job(pipeline, twitter_coll)
    finally:
        await reddit_coll.close()


async def run_scheduler(config: dict):
    """Run forever with scheduled jobs."""
    await db.init_db()
    state = await BotState.load()
    pipeline = Pipeline(config, state=state)
    reddit_coll = RedditRSSCollector(
        subreddits=config["reddit"]["subreddits"],
        posts_per_sub=config["reddit"]["posts_per_sub"],
        max_age_hours=config["reddit"]["max_age_hours"],
        request_delay=config["reddit"].get("request_delay_seconds", 1.5),
    )
    feeds_coll = FeedsRSSCollector(
        sources=config["feeds"]["sources"],
        max_age_hours=config["feeds"]["max_age_hours"],
        request_delay=config["feeds"].get("request_delay_seconds", 1.0),
    )
    twitter_coll = TwitterScrapeCollector(
        accounts=config["twitter"]["accounts"],
        tweets_per_account=config["twitter"].get("tweets_per_account", 10),
        max_age_hours=config["twitter"].get("max_age_hours", 6),
    )

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        reddit_job, "interval",
        minutes=config["schedule"]["reddit_interval_minutes"],
        args=[pipeline, reddit_coll],
        next_run_time=None,  # we run first manually below
    )
    scheduler.add_job(
        feeds_job, "interval",
        minutes=config["schedule"]["feeds_interval_minutes"],
        args=[pipeline, feeds_coll],
    )
    if config["twitter"].get("enabled", False):
        scheduler.add_job(
            twitter_job, "interval",
            minutes=config["schedule"]["twitter_interval_minutes"],
            args=[pipeline, twitter_coll],
        )
    scheduler.add_job(cleanup_job, "cron", hour=3)  # daily 3am
    scheduler.start()

    # Build Telegram Application for command handling
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    handlers = BotCommandHandlers(state, config)
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start",  handlers.cmd_start))
    app.add_handler(CommandHandler("status", handlers.cmd_status))
    app.add_handler(CommandHandler("pause",  handlers.cmd_pause))
    app.add_handler(CommandHandler("resume", handlers.cmd_resume))
    app.add_handler(CommandHandler("score",  handlers.cmd_score))
    app.add_handler(CommandHandler("top",    handlers.cmd_top))
    app.add_handler(CommandHandler("draft_top", handlers.cmd_draft_top))
    app.add_handler(CommandHandler("stats",  handlers.cmd_stats))

    logger.info("Bot started. Press Ctrl+C to stop.")
    async with app:
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)

        # Run first cycle immediately
        await reddit_job(pipeline, reddit_coll)
        await feeds_job(pipeline, feeds_coll)
        if config["twitter"].get("enabled", False):
            await twitter_job(pipeline, twitter_coll)

        # Send startup notification
        try:
            sender = TelegramSender()
            await sender.send_text(
                "🤖 <b>AI Deal Bot online</b>\nĐang theo dõi Reddit + HN + Dev.to + ProductHunt + GitHub.\n"
                "Gõ /start để xem danh sách lệnh."
            )
        except Exception as e:
            logger.error(f"Startup notification failed: {e}")

        try:
            while True:
                await asyncio.sleep(3600)
        except (KeyboardInterrupt, asyncio.CancelledError):
            logger.info("Shutting down...")
        finally:
            scheduler.shutdown()
            await reddit_coll.close()
            await app.updater.stop()
            await app.stop()


async def test_telegram():
    sender = TelegramSender()
    await sender.send_text(
        "✅ <b>Test thành công!</b>\nBot có thể gửi tin nhắn cho bạn."
    )
    logger.info("Test message sent.")


# ---------- CLI ----------
def main():
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true",
                        help="Run one cycle and exit")
    parser.add_argument("--test-telegram", action="store_true",
                        help="Send a test message and exit")
    args = parser.parse_args()

    config = load_config()

    if args.test_telegram:
        asyncio.run(test_telegram())
    elif args.once:
        asyncio.run(run_once(config))
    else:
        asyncio.run(run_scheduler(config))


if __name__ == "__main__":
    main()
