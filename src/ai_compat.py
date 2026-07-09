"""Compatibility helpers for chat providers.

The pateway.ai gateway routes by model *and* protocol: OpenAI-family models
(gpt-*, glm-*, qwen-*) speak the OpenAI ``/chat/completions`` API, while
``claude-*`` and ``deepseek-*`` only accept the Anthropic ``/messages`` API.
``AIChatClient`` picks the right SDK per model so callers stay protocol-agnostic.
"""

import json
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


def base_url_from_env(fallback: str = "") -> str:
    """Return BASE_URL from .env if set, otherwise the config fallback."""
    return (os.getenv("BASE_URL") or "").strip() or fallback


def model_from_env(fallback: str = "") -> str:
    """Return MODEL from .env if set, otherwise the config fallback."""
    return (os.getenv("MODEL") or "").strip() or fallback


def supports_custom_temperature(model: str) -> bool:
    """Các model reasoning họ gpt-5 / o1 / o3 chỉ chấp nhận temperature mặc định (=1),
    gửi kèm temperature khác sẽ bị 400. Trả False để bỏ qua field temperature."""
    m = (model or "").lower()
    return not (m.startswith("gpt-5") or m.startswith("o1") or m.startswith("o3"))


def json_response_format(base_url: str, model: str) -> Optional[dict]:
    """Return native JSON mode options when the configured provider supports it."""
    provider_hint = f"{base_url or ''} {model or ''}".lower()
    if "bynara" in provider_hint or "hhtechapi" in provider_hint:
        return None
    return {"type": "json_object"}


# Models that must be called via the Anthropic Messages API on this gateway.
_ANTHROPIC_MODEL_PREFIXES = ("claude", "deepseek")


def provider_protocol(model: str) -> str:
    """Return "anthropic" or "openai" for the given model.

    Overridable via the AI_PROTOCOL env var when the gateway adds models whose
    protocol isn't captured by the prefix heuristic below.
    """
    override = (os.getenv("AI_PROTOCOL") or "").strip().lower()
    if override in ("anthropic", "openai"):
        return override
    if (model or "").lower().startswith(_ANTHROPIC_MODEL_PREFIXES):
        return "anthropic"
    return "openai"


def loads_json_lenient(raw: str):
    """Parse a JSON object from a model reply, tolerating code fences / stray text."""
    text = (raw or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            return json.loads(text[start:end + 1])
        raise


def _anthropic_text(message) -> str:
    """Join the text blocks of an Anthropic message, skipping thinking blocks."""
    parts = []
    for block in getattr(message, "content", None) or []:
        if getattr(block, "type", None) == "text":
            parts.append(getattr(block, "text", "") or "")
    return "".join(parts).strip()


class AIChatClient:
    """Single-turn chat client that hides the OpenAI vs Anthropic protocol split."""

    def __init__(self, base_url: str, model: str, timeout: int = 30,
                 max_retries: int = 2):
        self.model = model
        self.base_url = base_url
        self.timeout = timeout
        self.protocol = provider_protocol(model)
        api_key = api_key_from_env()
        # base_url None/empty -> dùng endpoint mặc định của SDK tương ứng
        if self.protocol == "anthropic":
            from anthropic import AsyncAnthropic
            self.client = AsyncAnthropic(
                base_url=base_url or None, api_key=api_key,
                timeout=timeout, max_retries=max_retries)
        else:
            from openai import AsyncOpenAI
            self.client = AsyncOpenAI(
                base_url=base_url or None, api_key=api_key,
                timeout=timeout, max_retries=max_retries)

    async def complete(self, *, system: str, user: str,
                       temperature: Optional[float] = None,
                       max_tokens: int = 1024, want_json: bool = True) -> str:
        """Send one system+user turn and return the assistant's text reply."""
        if self.protocol == "anthropic":
            kwargs = {
                "model": self.model,
                "max_tokens": max_tokens,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            }
            if temperature is not None:
                kwargs["temperature"] = temperature
            message = await self.client.messages.create(**kwargs)
            return _anthropic_text(message)

        request = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if temperature is not None and supports_custom_temperature(self.model):
            request["temperature"] = temperature
        if want_json:
            response_format = json_response_format(self.base_url, self.model)
            if response_format:
                request["response_format"] = response_format
        resp = await self.client.chat.completions.create(**request)
        return resp.choices[0].message.content
