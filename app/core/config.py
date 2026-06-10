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

    # Sportmonks (ikinci veri kaynağı; token query-param + include ile çalışır,
    # API-Football'dan zengin: gerçek xG + oyuncu-başı istatistik). Token yalnız
    # backend'de tutulur, asla istemciye gitmez.
    sportmonks_api_key: str = Field(default="", alias="SPORTMONKS_API_KEY")
    sportmonks_base_url: str = Field(
        default="https://api.sportmonks.com/v3/football",
        alias="SPORTMONKS_BASE_URL",
    )
    # Aktif veri kaynağı (appearance ingest + backfill). "api_football" (varsayılan)
    # ya da "sportmonks". sync_league lig/takım/fikstür çekimi ayrıca yapılır;
    # bu yalnız maç kadro/istatistik ingest'inin kaynağını seçer.
    data_source: str = Field(default="api_football", alias="DATA_SOURCE")

    # Veritabanı
    database_url: str = Field(
        default="postgresql+psycopg://user:password@localhost:5432/manager2",
        alias="DATABASE_URL",
    )

    # Anthropic (Faz 3'te kullanılacak)
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")

    # LLM provider seçimi — şu an "anthropic" (default), "openai"/"gemini" iskelet
    llm_provider: str = Field(default="anthropic", alias="LLM_PROVIDER")

    # xG modeli (Prompt 2) — trained artifact path; boş ise models/xg_v1.pkl
    xg_model_path: str = Field(default="", alias="XG_MODEL_PATH")

    # Canlı feed sağlayıcısı — maç-içi konsolda hangi enterprise feed'in
    # (StatsBomb/Opta/Stats Perform) API anahtarı "bağlı" görünür. Veri bugün
    # StatsBomb open replay'inden gelir; bu sadece sunum/bağlantı katmanı.
    # Geçerli: "statsbomb" | "opta" | "stats_perform".
    live_feed_provider: str = Field(default="statsbomb", alias="LIVE_FEED_PROVIDER")
    # Sağlayıcı API anahtarı. Boş ise sağlayıcıya özgü demo key kullanılır
    # (replay demo'da .env gerektirmeden "bağlı" görünür). Snapshot'a yalnızca
    # MASKELİ hâli düşer (tam key asla istemciye gönderilmez).
    live_feed_api_key: str = Field(default="", alias="LIVE_FEED_API_KEY")
    # Canlı veri kaynağı modu. "replay" (varsayılan) = StatsBomb open event'leri
    # event-zaman güdümlü replay. "live_api" = gerçek koordinatlı event akışı
    # (Opta/StatsBomb Pro adapter'ı bağlandığında). Koordinatlı akış olmadan
    # tactical motorlar (xT/VAEP) beslenemez; bu yüzden adapter gelene kadar
    # "live_api" seçilse bile fabrika güvenli şekilde replay'e düşer.
    live_feed_mode: str = Field(default="replay", alias="LIVE_FEED_MODE")

    # Kota koruması
    api_football_daily_limit: int = Field(default=100, alias="API_FOOTBALL_DAILY_LIMIT")
    api_football_monthly_limit: int = Field(default=2000, alias="API_FOOTBALL_MONTHLY_LIMIT")
    anthropic_daily_token_limit: int = Field(default=200000, alias="ANTHROPIC_DAILY_TOKEN_LIMIT")

    # API erişim anahtarı (boş ise auth devre dışı — sadece dev için)
    api_auth_key: str = Field(default="", alias="API_AUTH_KEY")

    # Multi-tenant JWT auth (Ufuk 1)
    jwt_secret_key: str = Field(default="", alias="JWT_SECRET_KEY")
    jwt_access_minutes: int = Field(default=15, alias="JWT_ACCESS_MINUTES")
    jwt_refresh_days: int = Field(default=7, alias="JWT_REFRESH_DAYS")
    # Eski X-API-Key kullanımını DESTEKLE: bu değer set'liyse o key'i kabul
    # eder ve default tenant + admin user'a map eder. Geriye uyumluluk için.
    backward_compat_api_key: str = Field(
        default="", alias="BACKWARD_COMPAT_API_KEY",
    )

    # Notifications (Faz 5 #19) — boşsa kanal stub modda çalışır.
    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str = Field(default="", alias="TELEGRAM_CHAT_ID")
    twilio_account_sid: str = Field(default="", alias="TWILIO_ACCOUNT_SID")
    twilio_auth_token: str = Field(default="", alias="TWILIO_AUTH_TOKEN")
    whatsapp_from: str = Field(default="", alias="WHATSAPP_FROM")
    whatsapp_to: str = Field(default="", alias="WHATSAPP_TO")
    # E-posta (SMTP) — host/from/to boşsa kanal stub modda çalışır.
    smtp_host: str = Field(default="", alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_username: str = Field(default="", alias="SMTP_USERNAME")
    smtp_password: str = Field(default="", alias="SMTP_PASSWORD")
    smtp_from: str = Field(default="", alias="SMTP_FROM")
    smtp_to: str = Field(default="", alias="SMTP_TO")
    smtp_use_tls: bool = Field(default=True, alias="SMTP_USE_TLS")
    # Redis cache backend (opsiyonel). Boşsa DB-destekli cache kullanılır.
    redis_url: str = Field(default="", alias="REDIS_URL")

    # Geliştirme/test
    use_fixtures: bool = Field(default=False, alias="USE_FIXTURES")
    log_level: LogLevel = Field(default="INFO", alias="LOG_LEVEL")
    log_format: Literal["text", "json"] = Field(default="text", alias="LOG_FORMAT")

    # Production hardening
    rate_limit_per_minute: int = Field(default=120, alias="RATE_LIMIT_PER_MINUTE")
    # /auth/login için ayrı sıkı limit (brute-force yüzeyi daralt). IP başına/dk.
    login_rate_limit_per_minute: int = Field(
        default=10, alias="LOGIN_RATE_LIMIT_PER_MINUTE"
    )
    # DB connection pool (SQLite dışı backend'lerde uygulanır)
    db_pool_size: int = Field(default=5, alias="DB_POOL_SIZE")
    db_max_overflow: int = Field(default=10, alias="DB_MAX_OVERFLOW")
    db_pool_recycle_seconds: int = Field(default=1800, alias="DB_POOL_RECYCLE_SECONDS")
    # Dış HTTP (API-Football) retry + circuit breaker
    http_timeout_seconds: float = Field(default=10.0, alias="HTTP_TIMEOUT_SECONDS")
    http_retry_attempts: int = Field(default=3, alias="HTTP_RETRY_ATTEMPTS")
    http_breaker_threshold: int = Field(default=5, alias="HTTP_BREAKER_THRESHOLD")
    http_breaker_cooldown_seconds: float = Field(
        default=30.0, alias="HTTP_BREAKER_COOLDOWN_SECONDS"
    )
    # Hata izleme (Sentry) — DSN boşsa devre dışı (no-op). Opsiyonel.
    sentry_dsn: str = Field(default="", alias="SENTRY_DSN")
    sentry_traces_sample_rate: float = Field(
        default=0.0, ge=0.0, le=1.0, alias="SENTRY_TRACES_SAMPLE_RATE"
    )
    # Prometheus /metrics — prometheus-client kuruluysa aktif.
    prometheus_enabled: bool = Field(default=True, alias="PROMETHEUS_ENABLED")
    # Kota uyarı eşiği (0..1) — bu fraksiyona ulaşınca WARNING log
    # Default 0.8 = %80. 0.6 → daha erken uyarı; 0.9 → daha geç.
    quota_warn_fraction: float = Field(
        default=0.8, ge=0.0, le=1.0, alias="QUOTA_WARN_FRACTION"
    )

    # CORS — virgülle ayrılmış origin listesi.
    # Dev: "*" → tüm origins (kolay).
    # Prod: "https://app.example.com,https://admin.example.com" gibi whitelist.
    # Boş ise CORS middleware kayıtlı olmaz (browser client yok varsayımı).
    cors_allowed_origins: str = Field(default="", alias="CORS_ALLOWED_ORIGINS")

    def cors_origins_list(self) -> list[str]:
        """Comma-separated string → list, boş entry'leri filtrele."""
        return [s.strip() for s in self.cors_allowed_origins.split(",") if s.strip()]

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
        if not self.jwt_secret_key:
            errors.append(
                "JWT_SECRET_KEY boş — prod'da auth için zorunlu (32+ byte random)"
            )
        if errors:
            joined = "\n  - ".join(errors)
            raise ConfigError(
                f"APP_ENV=prod için config eksiklikleri:\n  - {joined}"
            )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
