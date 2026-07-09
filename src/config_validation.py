"""Configuration validation module to ensure config.yaml schema is correct on startup."""
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


class ConfigValidationError(ValueError):
    """Raised when configuration validation fails."""
    pass


def validate_config(config: Dict[str, Any]) -> None:
    """Validate all config values and raise ConfigValidationError on failure."""
    if not isinstance(config, dict):
        raise ConfigValidationError("Configuration must be a dictionary.")

    required_sections = ["schedule", "ai_filter", "posting", "reddit", "feeds", "keywords"]
    for section in required_sections:
        if section not in config:
            raise ConfigValidationError(f"Missing required config section: '{section}'")
        if not isinstance(config[section], dict):
            raise ConfigValidationError(f"Config section '{section}' must be a dictionary.")

    # 1. Validate schedule
    sched = config["schedule"]
    _check_type(sched, "reddit_interval_minutes", int, "schedule")
    _check_range(sched["reddit_interval_minutes"], 1, 1440, "schedule.reddit_interval_minutes")

    _check_type(sched, "feeds_interval_minutes", int, "schedule")
    _check_range(sched["feeds_interval_minutes"], 1, 1440, "schedule.feeds_interval_minutes")

    _check_type(sched, "batch_send_delay_seconds", (int, float), "schedule")
    _check_range(sched["batch_send_delay_seconds"], 0, 60, "schedule.batch_send_delay_seconds")

    _check_type(sched, "max_send_per_cycle", int, "schedule")
    _check_range(sched["max_send_per_cycle"], 1, 100, "schedule.max_send_per_cycle")

    _check_type(sched, "max_classify_per_cycle", int, "schedule")
    _check_range(sched["max_classify_per_cycle"], 1, 500, "schedule.max_classify_per_cycle")

    _check_type(sched, "max_per_source_per_cycle", int, "schedule")
    _check_range(sched["max_per_source_per_cycle"], 1, 100, "schedule.max_per_source_per_cycle")

    _check_type(sched, "max_per_topic_per_cycle", int, "schedule")
    _check_range(sched["max_per_topic_per_cycle"], 1, 100, "schedule.max_per_topic_per_cycle")

    _check_type(sched, "quiet_hours_start", int, "schedule")
    _check_range(sched["quiet_hours_start"], 0, 23, "schedule.quiet_hours_start")

    _check_type(sched, "quiet_hours_end", int, "schedule")
    _check_range(sched["quiet_hours_end"], 0, 23, "schedule.quiet_hours_end")

    _check_type(sched, "quiet_min_score", int, "schedule")
    _check_range(sched["quiet_min_score"], 1, 10, "schedule.quiet_min_score")

    _check_type(sched, "timezone", str, "schedule")

    # 2. Validate ai_filter
    ai = config["ai_filter"]
    _check_type(ai, "enabled", bool, "ai_filter")
    if ai["enabled"]:
        _check_type(ai, "base_url", str, "ai_filter")
        if not ai["base_url"].strip():
            raise ConfigValidationError("ai_filter.base_url cannot be empty when enabled.")
        _check_type(ai, "model", str, "ai_filter")
        if not ai["model"].strip():
            raise ConfigValidationError("ai_filter.model cannot be empty when enabled.")

    _check_type(ai, "min_score_to_notify", int, "ai_filter")
    _check_range(ai["min_score_to_notify"], 1, 10, "ai_filter.min_score_to_notify")

    _check_type(ai, "timeout_seconds", int, "ai_filter")
    _check_range(ai["timeout_seconds"], 1, 300, "ai_filter.timeout_seconds")

    # 3. Validate posting
    post = config["posting"]
    _check_type(post, "enabled", bool, "posting")
    if post["enabled"]:
        _check_type(post, "blog_dir", str, "posting")
        if not post["blog_dir"].strip():
            raise ConfigValidationError("posting.blog_dir cannot be empty when enabled.")

    _check_type(post, "default_hours", int, "posting")
    _check_range(post["default_hours"], 1, 168, "posting.default_hours")

    _check_type(post, "default_limit", int, "posting")
    _check_range(post["default_limit"], 1, 50, "posting.default_limit")

    _check_type(post, "min_score", int, "posting")
    _check_range(post["min_score"], 1, 10, "posting.min_score")

    _check_type(post, "min_items", int, "posting")
    _check_range(post["min_items"], 1, 50, "posting.min_items")

    _check_type(post, "timeout_seconds", int, "posting")
    _check_range(post["timeout_seconds"], 1, 300, "posting.timeout_seconds")

    _check_type(post, "include_drafted", bool, "posting")
    _check_type(post, "mark_drafted_on_create", bool, "posting")

    # 4. Validate reddit
    red = config["reddit"]
    _check_type(red, "posts_per_sub", int, "reddit")
    _check_range(red["posts_per_sub"], 1, 100, "reddit.posts_per_sub")

    _check_type(red, "max_age_hours", int, "reddit")
    _check_range(red["max_age_hours"], 1, 72, "reddit.max_age_hours")

    _check_type(red, "request_delay_seconds", (int, float), "reddit")
    _check_range(red["request_delay_seconds"], 0.0, 10.0, "reddit.request_delay_seconds")

    _check_type(red, "subreddits", list, "reddit")
    for sub in red["subreddits"]:
        if not isinstance(sub, str) or not sub.strip():
            raise ConfigValidationError(
                f"Invalid subreddit '{sub}' in reddit.subreddits list (must be a non-empty string)."
            )

    # 5. Validate feeds
    f = config["feeds"]
    _check_type(f, "max_age_hours", int, "feeds")
    _check_range(f["max_age_hours"], 1, 72, "feeds.max_age_hours")

    _check_type(f, "request_delay_seconds", (int, float), "feeds")
    _check_range(f["request_delay_seconds"], 0.0, 10.0, "feeds.request_delay_seconds")

    _check_type(f, "sources", list, "feeds")
    for idx, src in enumerate(f["sources"]):
        if not isinstance(src, dict):
            raise ConfigValidationError(f"Feed source at index {idx} must be a dictionary.")
        _check_type(src, "name", str, f"feeds.sources[{idx}]")
        _check_type(src, "url", str, f"feeds.sources[{idx}]")
        _check_type(src, "label", str, f"feeds.sources[{idx}]")
        if "max_items" in src:
            _check_type(src, "max_items", int, f"feeds.sources[{idx}]")
            _check_range(src["max_items"], 1, 100, f"feeds.sources[{idx}].max_items")

    # 7. Validate keywords (required by Pipeline)
    kw = config["keywords"]
    for list_name in ("whitelist", "blacklist"):
        _check_type(kw, list_name, list, "keywords")
        for word in kw[list_name]:
            if not isinstance(word, str) or not word.strip():
                raise ConfigValidationError(
                    f"Invalid keyword '{word}' in keywords.{list_name} (must be a non-empty string)."
                )

    logger.info("Configuration validation passed successfully.")


def _check_type(d: Dict[str, Any], key: str, expected_type: Any, parent: str) -> None:
    if key not in d:
        raise ConfigValidationError(f"Missing required key '{key}' in section '{parent}'.")
    val = d[key]
    if not isinstance(val, expected_type):
        if isinstance(expected_type, tuple):
            type_str = "/".join(t.__name__ for t in expected_type)
        else:
            type_str = expected_type.__name__
        raise ConfigValidationError(
            f"Config field '{parent}.{key}' must be of type {type_str}, but got {type(val).__name__}."
        )


def _check_range(val: Any, min_val: Any, max_val: Any, name: str) -> None:
    if val < min_val or val > max_val:
        raise ConfigValidationError(f"Config field '{name}' must be between {min_val} and {max_val} (got {val}).")
