import unittest
from src.models import Item
from src.filters.keyword import KeywordFilter


class TestKeywordFilter(unittest.TestCase):
    def setUp(self):
        self.filter = KeywordFilter(
            whitelist=["next.js", "react", "typescript", "ai"],
            blacklist=["crypto", "nft", "spam"]
        )

    def test_whitelist_match(self):
        # Whitelisted word in title
        item = Item(source="test", title="Learning React is fun", content="Web development tutorial", url="http://example.com")
        self.assertTrue(self.filter.passes(item))

        # Whitelisted word in content
        item = Item(source="test", title="Web dev tutorial", content="We will cover typescript", url="http://example.com")
        self.assertTrue(self.filter.passes(item))

    def test_blacklist_match(self):
        # Blacklisted word in title
        item = Item(source="test", title="Why Crypto is the future", content="React tutorial", url="http://example.com")
        self.assertFalse(self.filter.passes(item))

        # Blacklisted word in content
        item = Item(source="test", title="Learn typescript", content="Avoid this nft spam", url="http://example.com")
        self.assertFalse(self.filter.passes(item))

    def test_word_boundaries(self):
        # next.js should match but next.jscode or accessnext.js shouldn't
        item_ok = Item(source="test", title="Using Next.js", content="framework", url="http://example.com")
        self.assertTrue(self.filter.passes(item_ok))

        item_fail = Item(source="test", title="Next.jscode is nice", content="framework", url="http://example.com")
        self.assertFalse(self.filter.passes(item_fail))

        # css shouldn't match accessing
        filter_css = KeywordFilter(whitelist=["css"], blacklist=[])
        item_css_fail = Item(source="test", title="Accessing items", content="tutorial", url="http://example.com")
        self.assertFalse(filter_css.passes(item_css_fail))

    def test_no_match(self):
        item = Item(source="test", title="Python tutorial", content="Hello world", url="http://example.com")
        self.assertFalse(self.filter.passes(item))

    def test_filter_batch(self):
        items = [
            Item(source="test", title="React post", content="content", url="1"),
            Item(source="test", title="NFT spam", content="content", url="2"),
            Item(source="test", title="Python post", content="content", url="3"),
        ]
        passed = self.filter.filter_batch(items)
        self.assertEqual(len(passed), 1)
        self.assertEqual(passed[0].title, "React post")


if __name__ == "__main__":
    unittest.main()
