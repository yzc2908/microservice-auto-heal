"""
Claude API client with prompt caching and automatic retry logic.
Designed for high-token-throughput scenarios — each agent call may consume
tens of thousands of tokens analyzing repository context.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import anthropic
from anthropic.types import Message, MessageParam

from src.config import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2.0


@dataclass
class LLMResponse:
    content: str
    model: str
    usage: dict[str, int] = field(default_factory=dict)
    stop_reason: str = ""


class LLMClient:
    """Thin wrapper around the Anthropic Python SDK with caching support."""

    def __init__(self, model: str | None = None) -> None:
        settings = get_settings()
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._model = model or settings.llm_model
        self._max_output = settings.llm_max_output_tokens

    async def chat(
        self,
        messages: list[MessageParam],
        system: str | None = None,
        *,
        temperature: float = 0.3,
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        kwargs: dict[str, Any] = dict(
            model=self._model,
            max_tokens=self._max_output,
            messages=messages,
            temperature=temperature,
        )
        if system:
            kwargs["system"] = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
        if tools:
            kwargs["tools"] = self._convert_tools(tools)

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                msg: Message = await self._client.messages.create(**kwargs)
                text = "".join(
                    block.text for block in msg.content if hasattr(block, "text")
                )
                return LLMResponse(
                    content=text,
                    model=msg.model,
                    usage={
                        "input_tokens": msg.usage.input_tokens if msg.usage else 0,
                        "output_tokens": msg.usage.output_tokens if msg.usage else 0,
                    },
                    stop_reason=msg.stop_reason or "",
                )
            except anthropic.RateLimitError:
                if attempt == MAX_RETRIES:
                    raise
                wait = RETRY_BACKOFF_BASE ** attempt
                logger.warning("rate_limited", attempt=attempt, wait_s=wait)
                await asyncio.sleep(wait)
            except anthropic.APIError as exc:
                logger.error("api_error", attempt=attempt, error=str(exc))
                if attempt == MAX_RETRIES:
                    raise
                await asyncio.sleep(RETRY_BACKOFF_BASE)

        raise RuntimeError("unreachable")

    @staticmethod
    def _convert_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        converted: list[dict[str, Any]] = []
        for t in tools:
            converted.append({
                "name": t["name"],
                "description": t.get("description", ""),
                "input_schema": {
                    "type": "object",
                    "properties": t.get("parameters", {}).get("properties", {}),
                    "required": t.get("parameters", {}).get("required", []),
                },
            })
        return converted


_client_singleton: Optional[LLMClient] = None


def get_llm_client(model: str | None = None) -> LLMClient:
    global _client_singleton
    if _client_singleton is None or model is not None:
        _client_singleton = LLMClient(model=model)
    return _client_singleton
