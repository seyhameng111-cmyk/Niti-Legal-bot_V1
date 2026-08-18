from __future__ import annotations

import re
from functools import lru_cache

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "NITI Legal Router Bot"
    environment: str = "production"
    log_level: str = "INFO"

    telegram_bot_token: SecretStr
    telegram_webhook_secret: SecretStr
    public_base_url: str | None = None
    render_external_hostname: str | None = None
    auto_set_webhook: bool = True
    configure_bot_profile: bool = True
    webhook_queue_size: int = Field(default=500, ge=10, le=5000)
    worker_count: int = Field(default=4, ge=1, le=20)

    gas_literal_url: str
    gas_explain_url: str
    gas_api_key: SecretStr | None = None
    gas_api_key_field: str = "apiKey"
    gas_question_field: str = "question"
    gas_literal_response_path: str = "answer"
    gas_explain_response_path: str = "answer"
    gas_timeout_seconds: float = Field(default=90.0, ge=5.0, le=300.0)
    gemini_model: str = "gemini-3.5-flash-lite"

    bot_brand_name: str = "នីតិ AI"
    max_question_chars: int = Field(default=4000, ge=100, le=12000)
    rate_limit_questions: int = Field(default=6, ge=1, le=100)
    rate_limit_window_seconds: int = Field(default=60, ge=10, le=3600)

    @field_validator("telegram_webhook_secret")
    @classmethod
    def validate_webhook_secret(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value()
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,256}", raw):
            raise ValueError(
                "TELEGRAM_WEBHOOK_SECRET may contain only A-Z, a-z, 0-9, _ and -"
            )
        return value

    @field_validator("public_base_url")
    @classmethod
    def normalize_public_url(cls, value: str | None) -> str | None:
        return value.rstrip("/") if value else value

    @property
    def resolved_public_base_url(self) -> str | None:
        if self.public_base_url:
            return self.public_base_url
        if self.render_external_hostname:
            return f"https://{self.render_external_hostname.strip('/')}"
        return None

    @property
    def webhook_url(self) -> str | None:
        base = self.resolved_public_base_url
        return f"{base}/telegram/webhook" if base else None


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
