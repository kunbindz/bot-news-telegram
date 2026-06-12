"""Slug helpers for generated blog posts."""
import re
import unicodedata
from pathlib import Path


def slugify(text: str, max_length: int = 70) -> str:
    normalized = unicodedata.normalize("NFD", text or "")
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_text.lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    if not slug:
        slug = "ai-notes"
    return slug[:max_length].strip("-")


def unique_mdx_path(blog_dir: Path, title: str, date_str: str) -> Path:
    base = slugify(title)
    candidate = blog_dir / f"{date_str}-{base}.mdx"
    if not candidate.exists():
        return candidate
    index = 2
    while True:
        candidate = blog_dir / f"{date_str}-{base}-{index}.mdx"
        if not candidate.exists():
            return candidate
        index += 1
