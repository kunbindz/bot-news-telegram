import unittest
from src.config_validation import validate_config, ConfigValidationError


class TestConfigValidation(unittest.TestCase):
    def setUp(self):
        self.valid_config = {
            "schedule": {
                "reddit_interval_minutes": 15,
                "feeds_interval_minutes": 20,
                "batch_send_delay_seconds": 2,
                "max_send_per_cycle": 5,
                "max_per_source_per_cycle": 2,
                "max_per_topic_per_cycle": 1,
                "quiet_hours_start": 23,
                "quiet_hours_end": 7,
                "quiet_min_score": 9,
                "timezone": "Asia/Ho_Chi_Minh",
            },
            "ai_filter": {
                "enabled": True,
                "base_url": "https://hhtechapi.com/v1",
                "model": "deepseek-v4",
                "min_score_to_notify": 6,
                "timeout_seconds": 30,
            },
            "posting": {
                "enabled": True,
                "blog_dir": "E:/blog/frontend/content/blog",
                "default_hours": 24,
                "default_limit": 5,
                "min_score": 8,
                "min_items": 2,
                "timeout_seconds": 60,
                "include_drafted": False,
                "mark_drafted_on_create": True,
            },
            "reddit": {
                "posts_per_sub": 15,
                "max_age_hours": 6,
                "request_delay_seconds": 1.5,
                "subreddits": ["ChatGPT", "LocalLLaMA"],
            },
            "feeds": {
                "max_age_hours": 12,
                "request_delay_seconds": 1.0,
                "sources": [
                    {
                        "name": "hackernews",
                        "url": "https://hnrss.org/newest?points=100",
                        "label": "hn",
                        "max_items": 15,
                    }
                ],
            },
            "keywords": {
                "whitelist": ["claude", "react", "typescript"],
                "blacklist": ["crypto", "nft"],
            },
        }

    def test_valid_config(self):
        try:
            validate_config(self.valid_config)
        except ConfigValidationError as e:
            self.fail(f"validate_config raised ConfigValidationError unexpectedly: {e}")

    def test_missing_section(self):
        invalid = self.valid_config.copy()
        del invalid["schedule"]
        with self.assertRaises(ConfigValidationError) as ctx:
            validate_config(invalid)
        self.assertIn("Missing required config section", str(ctx.exception))

    def test_invalid_type(self):
        invalid = {**self.valid_config}
        invalid["schedule"] = {**self.valid_config["schedule"], "reddit_interval_minutes": "fifteen"}
        with self.assertRaises(ConfigValidationError) as ctx:
            validate_config(invalid)
        self.assertIn("must be of type int", str(ctx.exception))

    def test_out_of_range(self):
        invalid = {**self.valid_config}
        invalid["schedule"] = {**self.valid_config["schedule"], "quiet_hours_start": 25}
        with self.assertRaises(ConfigValidationError) as ctx:
            validate_config(invalid)
        self.assertIn("must be between 0 and 23", str(ctx.exception))

    def test_empty_string_when_enabled(self):
        invalid = {**self.valid_config}
        invalid["ai_filter"] = {**self.valid_config["ai_filter"], "enabled": True, "base_url": "   "}
        with self.assertRaises(ConfigValidationError) as ctx:
            validate_config(invalid)
        self.assertIn("base_url cannot be empty", str(ctx.exception))

    def test_missing_keywords_section(self):
        invalid = self.valid_config.copy()
        del invalid["keywords"]
        with self.assertRaises(ConfigValidationError) as ctx:
            validate_config(invalid)
        self.assertIn("Missing required config section", str(ctx.exception))

    def test_invalid_keyword_entry(self):
        invalid = {**self.valid_config}
        invalid["keywords"] = {"whitelist": ["react", ""], "blacklist": ["crypto"]}
        with self.assertRaises(ConfigValidationError) as ctx:
            validate_config(invalid)
        self.assertIn("Invalid keyword", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
