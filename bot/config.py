"""Typed application configuration, loaded from environment / .env.

All secrets live here and nowhere else. Import `settings` (the cached
singleton) rather than reading os.environ directly.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Telegram ---
    bot_token: SecretStr
    bot_username: str = "YourMusicBot"

    # --- Postgres ---
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "musicbot"
    postgres_user: str = "musicbot"
    postgres_password: SecretStr = SecretStr("change-me")

    # --- Redis ---
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_db: int = 0

    # --- Music metadata APIs ---
    spotify_client_id: str = ""
    spotify_client_secret: SecretStr = SecretStr("")
    lastfm_api_key: str = ""

    # --- Lyrics ---
    genius_access_token: SecretStr = SecretStr("")

    # --- Licensed full-track backend (operator supplied) ---
    licensed_source_base_url: str = ""
    licensed_source_api_key: SecretStr = SecretStr("")

    # --- VKontakte Music ---
    vk_token: str = ""
    vk_user_agent: str = ""

    # --- Runtime ---
    log_level: str = "INFO"
    healthcheck_port: int = 8080
    default_language: str = "en"

    # ---- Derived helpers ---------------------------------------------------
    @property
    def database_url(self) -> str:
        """SQLAlchemy async DSN (asyncpg driver)."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:"
            f"{self.postgres_password.get_secret_value()}@"
            f"{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def promo_caption_line(self) -> str:
        return f"🤖 @{self.bot_username} — Find any track instantly"

    @property
    def promo_comment(self) -> str:
        return f"Delivered by @{self.bot_username} 🎵 | t.me/{self.bot_username}"


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton (parsed once per process)."""
    return Settings()  # type: ignore[call-arg]


settings = get_settings()

# Languages the UI ships with (Fluent .ftl files in locales/).
SUPPORTED_LANGUAGES: tuple[str, ...] = ("en", "ru", "de", "es", "uk", "kk")
