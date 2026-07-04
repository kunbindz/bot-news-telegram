"""Generate blog drafts from scored news candidates."""
import json
import logging
import os
from typing import Any, Dict, List

from openai import AsyncOpenAI

from src.posting.blog_writer import DraftPost
from src.posting.prompts import DRAFT_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class DraftGenerationError(RuntimeError):
    pass


def _clean_json_text(raw: str) -> str:
    text = (raw or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def _parse_tags(raw: Any) -> List[str]:
    if not isinstance(raw, list):
        return ["ai", "workflow"]
    tags = []
    for tag in raw:
        value = str(tag).strip().lower()
        if value and value not in tags:
            tags.append(value)
    return tags[:6] or ["ai", "workflow"]


def _candidate_payload(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    payload = []
    for row in candidates:
        tags = row.get("summary_tags") or "[]"
        try:
            tags = json.loads(tags) if isinstance(tags, str) else tags
        except json.JSONDecodeError:
            tags = []
        payload.append({
            "source": row.get("source"),
            "title": row.get("title"),
            "url": row.get("url"),
            "author": row.get("author"),
            "score": row.get("score"),
            "category": row.get("category"),
            "content_excerpt": (row.get("content") or "")[:1800],
            "vn_summary": row.get("vn_summary"),
            "what_happened": row.get("summary_what"),
            "why_it_matters": row.get("summary_why"),
            "action": row.get("summary_action"),
            "tags": tags,
        })
    return payload


def _validate_draft(data: Dict[str, Any], candidates: List[Dict[str, Any]]) -> DraftPost:
    title = str(data.get("title") or "").strip()
    description = str(data.get("description") or "").strip()
    body = str(data.get("body") or "").strip()
    tags = _parse_tags(data.get("tags"))

    if not title:
        raise DraftGenerationError("Draft thiếu title.")
    if not description:
        raise DraftGenerationError("Draft thiếu description.")
    if len(body) < 800:
        raise DraftGenerationError("Draft quá ngắn, có thể chưa đủ chất lượng.")

    source_urls = [row.get("url") for row in candidates if row.get("url")]
    missing = [url for url in source_urls if url not in body]
    if missing:
        raise DraftGenerationError(
            "Draft thiếu link nguồn trong body: " + ", ".join(missing[:3])
        )

    return DraftPost(title=title, description=description, tags=tags, body=body)


class BlogDraftGenerator:
    def __init__(self, base_url: str, model: str, timeout: int = 45):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set in .env")
        self.model = model
        self.client = AsyncOpenAI(base_url=base_url or None, api_key=api_key, timeout=timeout)

    async def generate(self, candidates: List[Dict[str, Any]]) -> DraftPost:
        if not candidates:
            raise DraftGenerationError("Không có candidate để tạo draft.")

        payload = _candidate_payload(candidates)
        user_msg = (
            "Dưới đây là các nguồn đã được bot lọc và tóm tắt. "
            "Hãy viết bài chia sẻ học hỏi, bám sát nguồn.\n\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
        )
        resp = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": DRAFT_SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            response_format={"type": "json_object"},
            temperature=0.35,
        )
        raw = resp.choices[0].message.content
        try:
            data = json.loads(_clean_json_text(raw))
        except json.JSONDecodeError as exc:
            logger.error("Draft JSON parse failed: %s", raw)
            raise DraftGenerationError(f"AI trả JSON không hợp lệ: {exc}") from exc
        return _validate_draft(data, candidates)
