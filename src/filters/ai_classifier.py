"""AI classifier using Xiaomi MiMo (OpenAI-compatible API)."""
import os
import json
import logging
import asyncio
from typing import List

from openai import AsyncOpenAI

from src.models import Item

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """Bạn là filter tin tức cho một developer Việt Nam yêu thích AI và lập trình.
Người này quan tâm: AI news, model AI mới ra mắt, free trial, khóa học free,
deal/coupon Udemy, tăng quota/limit của AI tools, tips/tricks về dev/AI.

Phân loại tin sau và trả về CHỈ JSON (không kèm text khác):
{
  "category": "ai_news" | "model_release" | "free_trial" | "deal_course" | "tool_tip" | "quota_change" | "other",
  "relevance_score": <integer 1-10>,
  "vn_summary": "<2-3 câu tiếng Việt, giữ thuật ngữ kỹ thuật bằng English>",
  "should_notify": <true|false>
}

Quy tắc cho điểm:
- 9-10: model AI lớn ra mắt, free trial dài hạn có giá trị, tăng limit lớn từ Anthropic/OpenAI/Google
- 7-8: tin AI/dev có ích, free course chất lượng, tool mới đáng thử
- 5-6: tin liên quan nhưng không cấp bách
- 1-4: ít liên quan hoặc đã cũ
- should_notify = false nếu: meme, drama cá nhân, crypto/airdrop, tin scam,
  tin trùng lặp của tin lớn đã ra cách đây nhiều ngày."""


class MiMoClassifier:
    def __init__(self, base_url: str, model: str, timeout: int = 30):
        self.model = model
        self.timeout = timeout
        api_key = os.getenv("MIMO_API_KEY")
        if not api_key:
            raise RuntimeError("MIMO_API_KEY not set in .env")
        self.client = AsyncOpenAI(base_url=base_url, api_key=api_key,
                                  timeout=timeout)
        # Limit concurrent AI calls to avoid hammering
        self.semaphore = asyncio.Semaphore(5)

    async def classify(self, item: Item) -> Item:
        """Classify a single item. Mutates and returns the item."""
        async with self.semaphore:
            try:
                user_msg = (
                    f"Nguồn: {item.source}\n"
                    f"Tác giả: {item.author}\n"
                    f"Tiêu đề: {item.title}\n"
                    f"Nội dung: {item.content[:1200]}"
                )
                resp = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_msg},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.3,
                )
                raw = resp.choices[0].message.content
                data = json.loads(raw)

                item.category = data.get("category", "other")
                item.score = int(data.get("relevance_score", 0))
                item.vn_summary = data.get("vn_summary", "")
                item.should_notify = bool(data.get("should_notify", False))
            except Exception as e:
                logger.error(f"AI classify failed for [{item.title[:40]}]: {e}")
                # On error, default to NOT notifying so we don't spam
                item.should_notify = False
                item.score = 0
                item.category = "error"
            return item

    async def classify_batch(self, items: List[Item]) -> List[Item]:
        """Classify a batch in parallel (rate-limited via semaphore)."""
        if not items:
            return []
        tasks = [self.classify(it) for it in items]
        return await asyncio.gather(*tasks)
