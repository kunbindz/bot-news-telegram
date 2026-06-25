import unittest
from datetime import datetime, timezone
from src import db


class TestDBSync(unittest.TestCase):
    def test_make_hash(self):
        h1 = db.make_hash("http://test.com", "Title")
        h2 = db.make_hash("http://test.com", "Title")
        h3 = db.make_hash("http://test.com", "Different Title")
        self.assertEqual(h1, h2)
        self.assertNotEqual(h1, h3)
        self.assertEqual(len(h1), 16)


class TestDBAsync(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Use an in-memory database to avoid affecting actual files
        self.original_db_path = db.DB_PATH
        db.DB_PATH = ":memory:"
        # Reset the global connection singleton
        db._conn = None
        await db.init_db()

    async def asyncTearDown(self):
        await db.close_conn()
        db.DB_PATH = self.original_db_path
        db._conn = None

    async def test_mark_seen_and_is_seen(self):
        item_hash = db.make_hash("http://item1.com", "Title 1")
        self.assertFalse(await db.is_seen(item_hash))

        pub_time = datetime(2026, 6, 25, 12, 0, 0, tzinfo=timezone.utc)
        await db.mark_seen(
            item_hash=item_hash,
            source="test",
            title="Title 1",
            url="http://item1.com",
            published_at=pub_time,
            score=8,
            category="ai",
        )

        self.assertTrue(await db.is_seen(item_hash))

        # Retrieve and verify published_at
        candidates = await db.get_top_candidates(hours=24, min_score=7, include_drafted=True)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["hash"], item_hash)
        self.assertEqual(candidates[0]["published_at"], pub_time.isoformat())

    async def test_mark_seen_batch(self):
        items_data = [
            {
                "hash": db.make_hash("http://a.com", "A"),
                "source": "src",
                "title": "A",
                "url": "http://a.com",
                "score": 9,
                "category": "cat",
                "published_at": datetime(2026, 6, 25, 10, 0, 0, tzinfo=timezone.utc),
            },
            {
                "hash": db.make_hash("http://b.com", "B"),
                "source": "src",
                "title": "B",
                "url": "http://b.com",
                "score": 6,
                "category": "cat",
                "published_at": None,
            },
        ]

        await db.mark_seen_batch(items_data)

        # check seen
        self.assertTrue(await db.is_seen(items_data[0]["hash"]))
        self.assertTrue(await db.is_seen(items_data[1]["hash"]))

        # Check filtering seen hashes
        seen_hashes = await db.filter_seen_hashes([items_data[0]["hash"], "notseen"])
        self.assertEqual(seen_hashes, {items_data[0]["hash"]})

        # Check get_top_candidates
        candidates = await db.get_top_candidates(hours=24, min_score=8, include_drafted=True)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["title"], "A")
        self.assertEqual(candidates[0]["published_at"], "2026-06-25T10:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
