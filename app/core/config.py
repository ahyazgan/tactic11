"""Uygulama ayarları.

`.env` üzerinden okunan tüm yapılandırma tek noktadan akar. Modüller doğrudan
`os.environ` okumaz; `get_settings()` çağırır.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # API-Football
    api_football_key: str = Field(default="", alias="API_FOOTBALL_KEY")
    api_football_base_url: str = Field(
        default="https://v3.football.api-sports.io",
        alias="API_FOOTBALL_BASE_URL",
    )

    # Veritabanı
    database_url: str = Field(
        default="postgresql+psycopg://user:password@localhost:5432/manager2",
        alias="DATABASE_URL",
    )

    # Anthropic (Faz 3'te kullanılacak)
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")

    # Kota koruması
    api_football_daily_limit: int = Field(default=100, alias="API_FOOTBALL_DAILY_LIMIT")
    api_football_monthly_limit: int = Field(default=2000, alias="API_FOOTBALL_MONTHLY_LIMIT")
    anthropic_daily_token_limit: int = Field(default=200000, alias="ANTHROPIC_DAILY_TOKEN_LIMIT")

    # API erişim anahtarı (boş ise auth devre dışı — sadece dev için)
    api_auth_key: str = Field(default="", alias="API_AUTH_KEY")

    # Geliştirme/test
    use_fixtures: bool = Field(default=False, alias="USE_FIXTURES")
    log_level: LogLevel = Field(default="INFO", alias="LOG_LEVEL")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
