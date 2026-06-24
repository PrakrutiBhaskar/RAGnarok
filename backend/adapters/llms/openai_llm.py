"""OpenAI LLM adapter for oracle injection generation."""

from __future__ import annotations

import logging
import os
from typing import Any

from backend.adapters.base import (
    AdapterAuthError,
    AdapterRateLimitError,
    AdapterUnavailableError,
    LLMAdapter,
)
from backend.models.config import LLMConfig

logger = logging.getLogger(__name__)


class OpenAILLMAdapter(LLMAdapter):
    """LLM adapter for OpenAI chat completion models."""

    def __init__(self, config: LLMConfig) -> None:
        self._config = config
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client

        try:
            from openai import AsyncOpenAI
        except ImportError as e:
            raise ImportError("openai is not installed. Run: pip install openai") from e

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise AdapterAuthError(
                "openai", "init", "OPENAI_API_KEY environment variable is not set"
            )

        self._client = AsyncOpenAI(api_key=api_key)
        return self._client

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> str:
        client = self._get_client()

        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            response = await client.chat.completions.create(
                model=self._config.model_id,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            content = response.choices[0].message.content
            return content or ""

        except Exception as e:
            err_str = str(e).lower()
            if "authentication" in err_str or "401" in err_str:
                raise AdapterAuthError("openai", "generate", str(e)) from e
            if "rate limit" in err_str or "429" in err_str:
                raise AdapterRateLimitError("openai", "generate", str(e)) from e
            if "connection" in err_str or "timeout" in err_str:
                raise AdapterUnavailableError("openai", "generate", str(e)) from e
            raise

    async def health_check(self) -> bool:
        try:
            await self.generate("Say 'ok'", max_tokens=5)
            return True
        except Exception as e:
            logger.warning("OpenAILLMAdapter health check failed: %s", e)
            return False

    @property
    def model_id(self) -> str:
        return self._config.model_id

    @property
    def provider_name(self) -> str:
        return "openai"
