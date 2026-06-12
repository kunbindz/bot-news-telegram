"""Write generated drafts into the blog repository."""
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List

from src.posting.slug import unique_mdx_path


@dataclass
class DraftPost:
    title: str
    description: str
    tags: List[str]
    body: str


def _yaml_string(value: str) -> str:
    return json.dumps(value or "", ensure_ascii=False)


def _yaml_list(values: List[str]) -> str:
    clean = [str(v).strip() for v in values if str(v).strip()]
    return json.dumps(clean, ensure_ascii=False)


def estimate_reading_time(text: str) -> int:
    words = len((text or "").split())
    return max(1, round(words / 220))


def write_draft(blog_dir: str, draft: DraftPost) -> Path:
    target_dir = Path(blog_dir).expanduser()
    target_dir.mkdir(parents=True, exist_ok=True)

    date_str = datetime.now().strftime("%Y-%m-%d")
    path = unique_mdx_path(target_dir, draft.title, date_str)
    reading_time = estimate_reading_time(draft.body)
    tags = draft.tags or ["ai", "workflow"]

    content = (
        "---\n"
        f"title: {_yaml_string(draft.title)}\n"
        f"description: {_yaml_string(draft.description)}\n"
        f'pubDate: "{date_str}"\n'
        f"tags: {_yaml_list(tags)}\n"
        f"readingTime: {reading_time}\n"
        "featured: false\n"
        "---\n\n"
        f"{draft.body.strip()}\n"
    )
    path.write_text(content, encoding="utf-8")
    return path
