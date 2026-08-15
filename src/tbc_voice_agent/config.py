"""Application settings loaded from environment."""

from __future__ import annotations

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bind_host: str = "127.0.0.1"
    voice_api_port: int = 8000
    mock_tbc_port: int = 8090
    web_port: int = 5173

    mock_tbc_base_url: str = "http://127.0.0.1:8090"
    mock_tbc_bearer_token: str = "dev-mock-tbc-token"

    transport_provider: str = "text"
    stt_provider: str = "fake"
    llm_provider: str = "fake"
    tts_provider: str = "fake"
    voice_language: str = "en-US"
    policy_version: str = "poc-v1"
    content_version: str = "en-poc-v1"
    # ISO date used as "today" for PTP bounds. Empty means date.today().
    policy_as_of_date: str = ""

    openai_api_key: str = ""
    openai_llm_model: str = "gpt-4o-mini"
    openai_stt_model: str = "whisper-1"
    openai_tts_model: str = "tts-1"
    openai_tts_voice: str = "alloy"

    voice_db_path: str = "data/voice_agent.sqlite"
    mock_db_path: str = "data/mock_tbc.sqlite"

    cors_origins: str = "http://127.0.0.1:5173,http://localhost:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def has_openai(self) -> bool:
        return bool(self.openai_api_key.strip())

    @model_validator(mode="after")
    def enable_openai_when_keyed(self) -> Settings:
        """If a key is present, turn on OpenAI adapters when still at fake defaults."""
        if self.has_openai:
            if self.stt_provider == "fake":
                self.stt_provider = "openai"
            if self.llm_provider == "fake":
                self.llm_provider = "openai"
            if self.tts_provider == "fake":
                self.tts_provider = "openai"
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
