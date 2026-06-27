"""
Application settings — loaded from environment variables / .env file.
All API keys are handled here and NEVER hardcoded elsewhere.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── API Keys ─────────────────────────────────────────────────────────────
    openai_api_key: str | None = Field(None, alias="OPENAI_API_KEY")
    anthropic_api_key: str | None = Field(None, alias="ANTHROPIC_API_KEY")
    pinecone_api_key: str | None = Field(None, alias="PINECONE_API_KEY")
    cohere_api_key: str | None = Field(None, alias="COHERE_API_KEY")

    # ── App Settings ─────────────────────────────────────────────────────────
    rag_debugger_home: Path = Field(
        default_factory=lambda: Path.home() / ".rag-debugger",
        alias="RAG_DEBUGGER_HOME",
    )
    log_level: str = Field("INFO", alias="RAG_DEBUGGER_LOG_LEVEL")
    max_corpus_chunks: int = Field(100_000, alias="RAG_DEBUGGER_MAX_CORPUS_CHUNKS")
    sql_echo: bool = Field(False, alias="RAG_DEBUGGER_SQL_ECHO")

    # ── Server Settings ───────────────────────────────────────────────────────
    host: str = "127.0.0.1"
    port: int = 8765
    reload: bool = False

    # ── Telemetry ─────────────────────────────────────────────────────────────
    telemetry_enabled: bool = Field(False, alias="RAG_DEBUGGER_TELEMETRY")

    # ── Version ──────────────────────────────────────────────────────────────
    version: str = "1.0.0"

    def ensure_home_dir(self) -> Path:
        """Create home directory if it doesn't exist."""
        self.rag_debugger_home.mkdir(parents=True, exist_ok=True)
        logs_dir = self.rag_debugger_home / "logs"
        logs_dir.mkdir(exist_ok=True)
        return self.rag_debugger_home


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached singleton settings instance."""
    return Settings()