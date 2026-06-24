"""AI classifier using Nara Router (OpenAI-compatible API)."""
import os
import json
import logging
import asyncio
from typing import List

from openai import AsyncOpenAI

from src.models import Item

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """Bạn là filter tin tức cho một developer Việt Nam yêu thích AI và Front-End.
Người này quan tâm: AI news, model AI mới ra mắt, free trial, khóa học free,
deal/coupon Udemy, tăng quota/limit của AI tools, tips/tricks về dev/AI,
và đặc biệt là tin Front-End: JavaScript/TypeScript, React/Next.js/Vue/Svelte/Astro,
CSS/Tailwind, web performance, accessibility (a11y), animation, UI/UX, design system,
browser API, build tools (Vite/Webpack).
Ưu tiên cao hơn cho tin liên quan Claude, Anthropic, Claude Code, MCP,
model context, agentic coding, prompt/coding workflow, API/platform changes.

Phân loại tin sau và trả về CHỈ JSON (không kèm text khác):
{
  "category": "ai_news" | "model_release" | "free_trial" | "deal_course" | "tool_tip" | "quota_change" | "frontend" | "other",
  "relevance_score": <integer 1-10>,
  "vn_summary": "<tóm tắt tiếng Việt chi tiết, giữ thuật ngữ kỹ thuật bằng English>",
  "what_happened": "<1-2 câu ngắn: tin gì mới>",
  "why_it_matters": "<1-2 câu ngắn: tác động thực tế cho developer>",
  "action": "<1 câu ngắn: nên thử, theo dõi, nâng cấp, hay bỏ qua>",
  "tags": ["<tag1>", "<tag2>", "<tag3>"],
  "should_notify": <true|false>
}

Yêu cầu cho vn_summary:
- Viết 3-5 câu hoặc 3-4 gạch đầu dòng ngắn, đủ chi tiết để hiểu tin mà chưa cần mở link.
- Nêu rõ: tin gì mới, ai/công cụ nào liên quan, tác động thực tế cho developer, và nếu có thì điều kiện/giá/limit/cách dùng.
- Không viết chung chung kiểu "bài viết nói về..." nếu có thể nêu chi tiết cụ thể từ nội dung.
- Nếu nguồn là release/issue/changelog, ưu tiên nêu thay đổi chính, breaking change, bug fix, hoặc cách nâng cấp.
- `what_happened`, `why_it_matters`, `action` phải ngắn, rõ, tránh lặp lại y nguyên `vn_summary`.
- `tags` nên là 2-4 tag ngắn như `claude`, `anthropic`, `mcp`, `agent`, `api`, `release`, `free-trial`.

Quy tắc cho điểm:
- 9-10: model AI lớn ra mắt, free trial dài hạn có giá trị, tăng limit lớn từ Anthropic/OpenAI/Google
- 8-9: tin quan trọng về Claude/Anthropic/Claude Code/MCP, API/platform update đáng áp dụng ngay;
  hoặc tin Front-End lớn (release framework chính React/Vue/Svelte/Next, tính năng CSS/browser mới quan trọng)
- 7-8: tin AI/dev có ích, free course chất lượng, tool mới đáng thử;
  hoặc bài Front-End chất lượng (kỹ thuật mới, best practice, performance/a11y, deep-dive đáng đọc)
- 5-6: tin liên quan nhưng không cấp bách (gồm tip/tutorial FE cơ bản)
- 1-4: ít liên quan hoặc đã cũ
- should_notify = false nếu: meme, drama cá nhân, crypto/airdrop, tin scam,
  tin trùng lặp của tin lớn đã ra cách đây nhiều ngày, hoặc tutorial FE quá sơ đẳng/trùng lặp."""


class AIClassifier:
    def __init__(self, base_url: str, model: str, timeout: int = 30):
        self.model = model
        self.timeout = timeout
        api_key = os.getenv("NARA_API_KEY")
        if not api_key:
            raise RuntimeError("NARA_API_KEY not set in .env")
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
