"""Shared data structures."""
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional


@dataclass
class Item:
    """A piece of content from any source."""
    source: str          # e.g. "reddit:r/ClaudeAI" or "twitter:@AnthropicAI"
    title: str
    content: str
    url: str
    author: str = ""
    published_at: Optional[datetime] = None  # original publish time from source
    # Filled in by AI filter
    category: Optional[str] = None
    score: Optional[int] = None
    vn_summary: Optional[str] = None
    summary_what: Optional[str] = None
    summary_why: Optional[str] = None
    summary_action: Optional[str] = None
    summary_tags: Optional[List[str]] = None
    should_notify: bool = True

    @property
    def short_source(self) -> str:
        """Short source label for display."""
        return self.source.split(":")[-1] if ":" in self.source else self.source
