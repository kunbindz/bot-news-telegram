"""AI classifier using Xiaomi MiMo (OpenAI-compatible API)."""
import os
import json
import logging
import asyncio
from typing import List

from openai import AsyncOpenAI

from src.models import Item

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """Bạn là filter tin tức cho một Software Tester / QA Engineer người Việt.
Người này quan tâm: testing & QA (manual + automation), test automation tools
(Selenium, Cypress, Playwright, Appium, Robot Framework, JUnit/TestNG/Pytest),
API testing & Postman (Newman, mock server, REST/GraphQL, OpenAPI/Swagger),
SQL & database (PostgreSQL, MySQL, SQL Server, query tuning, index, join,
stored procedure), performance/load testing (JMeter, k6), CI/CD cho test,
best practices, tutorial, khóa học free, và tips/tricks nghề QA.
Ưu tiên cao hơn cho: tool mới/bản release đáng nâng cấp, kỹ thuật test thực dụng,
mẹo viết query SQL hiệu quả, và tài nguyên học miễn phí chất lượng.

Phân loại tin sau và trả về CHỈ JSON (không kèm text khác):
{
  "category": "qa_testing" | "test_automation" | "api_postman" | "sql_database" | "tool_release" | "course_tutorial" | "career_tip" | "other",
  "relevance_score": <integer 1-10>,
  "vn_summary": "<tóm tắt tiếng Việt chi tiết, giữ thuật ngữ kỹ thuật bằng English>",
  "what_happened": "<1-2 câu ngắn: tin gì mới>",
  "why_it_matters": "<1-2 câu ngắn: tác động thực tế cho một tester/QA>",
  "action": "<1 câu ngắn: nên thử, học, theo dõi, hay bỏ qua>",
  "tags": ["<tag1>", "<tag2>", "<tag3>"],
  "should_notify": <true|false>
}

Yêu cầu cho vn_summary:
- Viết 3-5 câu hoặc 3-4 gạch đầu dòng ngắn, đủ chi tiết để hiểu tin mà chưa cần mở link.
- Nêu rõ: tin gì mới, công cụ/kỹ thuật nào liên quan, tác động thực tế cho công việc test, và nếu có thì cách áp dụng/ví dụ.
- Không viết chung chung kiểu "bài viết nói về..." nếu có thể nêu chi tiết cụ thể từ nội dung.
- Nếu nguồn là release/changelog, ưu tiên nêu thay đổi chính, breaking change, tính năng mới hữu ích cho test, hoặc cách nâng cấp.
- `what_happened`, `why_it_matters`, `action` phải ngắn, rõ, tránh lặp lại y nguyên `vn_summary`.
- `tags` nên là 2-4 tag ngắn như `automation`, `playwright`, `postman`, `sql`, `performance`, `release`, `tutorial`.

Quy tắc cho điểm:
- 9-10: bản release lớn của tool test phổ biến (Playwright/Cypress/Selenium/Postman), kỹ thuật/tài nguyên cực hữu ích, khóa học free chất lượng cao
- 8-9: tin quan trọng về QA/automation/API testing/SQL đáng áp dụng ngay
- 7-8: tin testing/dev có ích, tutorial hay, tip SQL/automation đáng thử
- 5-6: tin liên quan nhưng không cấp bách
- 1-4: ít liên quan tới testing/SQL/Postman hoặc đã cũ
- should_notify = false nếu: meme, drama cá nhân, crypto/airdrop, tin scam,
  tin thuần marketing không có giá trị kỹ thuật, tin trùng lặp đã ra cách đây nhiều ngày."""


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
                    f"Nội dung: {item.content[:3000]}"
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
                item.summary_what = data.get("what_happened", "")
                item.summary_why = data.get("why_it_matters", "")
                item.summary_action = data.get("action", "")
                raw_tags = data.get("tags", [])
                item.summary_tags = (
                    [str(tag).strip() for tag in raw_tags if str(tag).strip()]
                    if isinstance(raw_tags, list) else []
                )
                item.should_notify = bool(data.get("should_notify", False))
            except Exception as e:
                logger.error(f"AI classify failed for [{item.title[:40]}]: {e}")
                # On error, default to NOT notifying so we don't spam
                item.should_notify = False
                item.score = 0
                item.category = "error"
                item.summary_tags = []
            return item

    async def classify_batch(self, items: List[Item]) -> List[Item]:
        """Classify a batch in parallel (rate-limited via semaphore)."""
        if not items:
            return []
        tasks = [self.classify(it) for it in items]
        return await asyncio.gather(*tasks)
