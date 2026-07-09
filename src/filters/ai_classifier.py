"""AI classifier — works over both OpenAI and Anthropic gateway protocols."""
import logging
import asyncio
from typing import List

from src.ai_compat import AIChatClient, loads_json_lenient
from src.models import Item

logger = logging.getLogger(__name__)


def _as_text(value) -> str:
    """Coerce a model field to a string.

    Some models return summary fields as a JSON array of bullet points
    instead of a string; join those into newline-separated text so they
    can be stored and rendered safely.
    """
    if value is None:
        return ""
    if isinstance(value, list):
        return "\n".join(
            f"- {str(v).strip()}" for v in value if str(v).strip()
        )
    return str(value)


SYSTEM_PROMPT = """Bạn là filter tin tức cho một developer Việt Nam yêu thích AI, lập trình, và Frontend development.
Người này quan tâm:
- AI news, model AI mới ra mắt, free trial, khóa học free, deal/coupon Udemy,
  tăng quota/limit của AI tools, tips/tricks về dev/AI.
- Frontend: React, Next.js, Vue, Svelte, TypeScript, JavaScript, CSS, Tailwind,
  Vite, web performance, browser updates, UI/UX patterns, component libraries,
  SSR/SSG/ISR, bundler/tooling updates, accessibility, PWA.
- TypeScript ecosystem: NestJS, tRPC, Prisma, Drizzle, Zod, GraphQL, Fastify,
  Hono, Elysia, React Native, Expo, Deno, Bun, Turbopack, Turborepo,
  testing (Vitest/Playwright/Jest), linting (ESLint/Biome), monorepo, T3 Stack.

Ưu tiên cao hơn cho:
- AI: tin liên quan Claude, Anthropic, Claude Code, MCP, model context,
  agentic coding, prompt/coding workflow, API/platform changes.
- Frontend: major framework releases (React, Next.js, Vue, Svelte),
  browser engine updates (V8, WebKit, Chrome DevTools), CSS new features,
  performance best practices, TypeScript updates, build tool changes (Vite, Turbopack).
- TS Ecosystem: NestJS/tRPC/Prisma/Drizzle major releases, Deno/Bun runtime updates,
  React Native/Expo releases, new TS features, testing framework updates,
  full-stack patterns (T3 Stack, monorepo setups).

Phân loại tin sau và trả về CHỈ JSON (không kèm text khác):
{
  "category": "ai_news" | "model_release" | "free_trial" | "deal_course" | "tool_tip" | "quota_change" | "frontend_release" | "frontend_tutorial" | "browser_update" | "css_feature" | "js_ecosystem" | "ts_backend" | "other",
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
- `tags` nên là 2-4 tag ngắn như `claude`, `anthropic`, `mcp`, `agent`, `api`, `release`, `free-trial`,
  `react`, `nextjs`, `css`, `typescript`, `vite`, `browser`, `performance`, `a11y`,
  `nestjs`, `trpc`, `prisma`, `drizzle`, `deno`, `bun`, `graphql`, `react-native`, `expo`, `monorepo`.

Quy tắc cho điểm:
- 9-10: model AI lớn ra mắt, free trial dài hạn có giá trị, tăng limit lớn từ Anthropic/OpenAI/Google,
        major framework release (React/Next.js/Vue major version), breaking browser changes,
        TypeScript major version, NestJS/Deno/Bun major release
- 8-9: tin quan trọng về Claude/Anthropic/Claude Code/MCP, API/platform update đáng áp dụng ngay,
       significant frontend tool/library release, new CSS features shipped in stable browsers,
       Prisma/Drizzle/tRPC major updates, React Native/Expo major releases
- 7-8: tin AI/dev có ích, free course chất lượng, tool mới đáng thử,
       useful frontend tutorials/patterns, TypeScript/Vite updates, performance tips thực tế,
       NestJS/GraphQL patterns, testing/linting tool updates, monorepo best practices
- 5-6: tin liên quan nhưng không cấp bách, minor library updates, general webdev discussion,
       minor patch releases, basic tutorials
- 1-4: ít liên quan hoặc đã cũ, beginner-only content, off-topic
- should_notify = false nếu: meme, drama cá nhân, crypto/airdrop, tin scam,
  tin trùng lặp của tin lớn đã ra cách đây nhiều ngày, hoặc tutorial FE quá sơ đẳng/trùng lặp."""


class AIClassifier:
    def __init__(self, base_url: str, model: str, timeout: int = 30):
        self.model = model
        self.timeout = timeout
        # max_retries cao hơn để chịu được rate limit (429) của gói free
        self.client = AIChatClient(base_url=base_url, model=model,
                                   timeout=timeout, max_retries=5)
        # Giới hạn concurrency thấp để tránh vượt per-minute limit của gói free
        self.semaphore = asyncio.Semaphore(2)

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
                # disable_thinking: phân loại là tác vụ JSON có cấu trúc, không cần
                # reasoning tokens -> cắt ~50% output token (đắt nhất) mà vẫn đủ chất lượng.
                raw = await self.client.complete(
                    system=SYSTEM_PROMPT, user=user_msg,
                    temperature=0.3, max_tokens=768, disable_thinking=True,
                )
                data = loads_json_lenient(raw)

                item.category = data.get("category", "other")
                item.score = int(data.get("relevance_score", 0))
                item.vn_summary = _as_text(data.get("vn_summary"))
                item.summary_what = _as_text(data.get("what_happened"))
                item.summary_why = _as_text(data.get("why_it_matters"))
                item.summary_action = _as_text(data.get("action"))
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
