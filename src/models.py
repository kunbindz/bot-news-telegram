"""Shared data structures."""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Item:
    """A piece of content from any source."""
    source: str          # e.g. "reddit:r/ClaudeAI" or "twitter:@AnthropicAI"
    title: str
    content: str
    url: str
    author: str = ""
    # Filled in by AI filter
    category: Optional[str] = None
    score: Optional[int] = None
    vn_summary: Optional[str] = None
    should_notify: bool = True

    @property
    def short_source(self) -> str:
        """Short source label for display."""
        return self.source.split(":")[-1] if ":" in self.source else self.source
