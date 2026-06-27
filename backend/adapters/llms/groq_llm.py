"""Groq LLM adapter — fast inference, free tier, ideal for oracle injection."""

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

# Groq free tier models (as of 2025)
GROQ_MODELS = {
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "llama3-8b-8192",
    "llama3-70b-8192",
    "mixtral-8x7b-32768",
    "gemma2-9b-it",
}


class GroqLLMAdapter(LLMAdapter):
    """LLM adapter for Groq inference API."""

    def __init__(self, config: LLMConfig) -> None:
        self._config = config
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client

        try:
            from groq import AsyncGroq
        except ImportError as e:
            raise ImportError(
                "groq is not installed. Run: pip install groq"
            ) from e

        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise AdapterAuthError(
                "groq", "init", "GROQ_API_KEY environment variable is not set. "
                "Get a free key at https://console.groq.com"
            )

        self._client = AsyncGroq(api_key=api_key)
        return self._client

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> str:
        client = self._get_client()

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        # Groq free tier has token limits — cap max_tokens
        max_tokens = min(max_tokens, 2048)

        try:
            response = await client.chat.completions.create(
                model=self._config.model_id,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content or ""

        except Exception as e:
            err_str = str(e).lower()
            if "authentication" in err_str or "401" in err_str or "invalid api key" in err_str:
                raise AdapterAuthError("groq", "generate", str(e)) from e
            if "rate limit" in err_str or "429" in err_str:
                raise AdapterRateLimitError("groq", "generate", str(e)) from e
            if "connection" in err_str or "timeout" in err_str:
                raise AdapterUnavailableError("groq", "generate", str(e)) from e
            raise

    async def health_check(self) -> bool:
        try:
            await self.generate("Say ok", max_tokens=5)
            return True
        except Exception as e:
            logger.warning("GroqLLMAdapter health check failed: %s", e)
            return False

    @property
    def model_id(self) -> str:
        return self._config.model_id

    @property
    def provider_name(self) -> str:
        return "groq"