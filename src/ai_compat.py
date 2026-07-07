"""Compatibility helpers for OpenAI-compatible chat providers."""

import os

from typing import Optional


def api_key_from_env() -> str:
    """Return the configured API key, preferring the generic provider key."""
    api_key = (
        os.getenv("API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or os.getenv("NARA_API_KEY")
    )
    if not api_key:
        raise RuntimeError("API_KEY not set in .env")
    return api_key


def json_response_format(base_url: str, model: str) -> Optional[dict]:
    """Return native JSON mode options when the configured provider supports it."""
    provider_hint = f"{base_url or ''} {model or ''}".lower()
    if "bynara" in provider_hint or "hhtechapi" in provider_hint:
        return None
    return {"type": "json_object"}
