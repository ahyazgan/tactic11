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
AppEnv = Literal["dev", "staging", "prod"]


class ConfigError(RuntimeError):
    """Production'da zorunlu config eksikse fail-fast için."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Ortam — prod modunda validate_for_production() zorunlu secret'ları
    # kontrol eder; eksikse boot başarısız.
    app_env: AppEnv = Field(default="dev", alias="APP_ENV")

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
    log_format: Literal["text", "json"] = Field(default="text", alias="LOG_FORMAT")

    # Production hardening
    rate_limit_per_minute: int = Field(default=120, alias="RATE_LIMIT_PER_MINUTE")

    def validate_for_production(self) -> None:
        """`app_env == "prod"` ise zorunlu secret'ları doğrula; eksikse fail.

        Dev/staging modlarda herhangi bir kontrol yok — geliştirici esnek
        çalışsın diye. Production'a girince hata ÇIKMASI istenir (sessiz
        unsafe boot olmasın).

        Kurallar:
        - `api_auth_key` boş olamaz (auth açık olmalı)
        - `database_url` SQLite olamaz (sqlite:// ile başlayamaz)
        - `use_fixtures` False olmalı (gerçek veriye gidilmeli)
        - `api_football_key` boş ise: USE_FIXTURES zaten False'sa anlamsız
          (sync başarısız olur); not olarak işaretle
        """
        if self.app_env != "prod":
            return

        errors: list[str] = []
        if not self.api_auth_key:
            errors.append("API_AUTH_KEY zorunlu (prod'da auth açık olmalı)")
        if self.database_url.startswith("sqlite"):
            errors.append("DATABASE_URL postgres olmalı (SQLite prod için değil)")
        if self.use_fixtures:
            errors.append("USE_FIXTURES=true prod'da kullanılamaz (gerçek veri lazım)")
        if not self.api_football_key:
            errors.append(
                "API_FOOTBALL_KEY boş — USE_FIXTURES=false ise sync başarısız olur"
            )
        if errors:
            joined = "\n  - ".join(errors)
            raise ConfigError(
                f"APP_ENV=prod için config eksiklikleri:\n  - {joined}"
            )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
