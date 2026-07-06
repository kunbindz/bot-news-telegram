"""Compatibility helpers for OpenAI-compatible chat providers."""

from typing import Optional


def json_response_format(base_url: str, model: str) -> Optional[dict]:
    """Return native JSON mode options when the configured provider supports it."""
    provider_hint = f"{base_url or ''} {model or ''}".lower()
    if "bynara" in provider_hint:
        return None
    return {"type": "json_object"}
