"""Settings.validate_for_production() — prod modunda fail-fast kontrolü."""

from __future__ import annotations

import pytest

from app.core.config import ConfigError, Settings


def _make(**overrides) -> Settings:
    """Tüm zorunlu alanları minimum geçerli değerle dolduran factory."""
    base = {
        "APP_ENV": "prod",
        "API_AUTH_KEY": "secret-32-bytes-strong",
        "DATABASE_URL": "postgresql://u:p@h:5432/db",
        "USE_FIXTURES": False,
        "API_FOOTBALL_KEY": "real-key",
        "JWT_SECRET_KEY": "test-secret-32-bytes-min-for-prod-mode",
    }
    base.update(overrides)
    return Settings(**{k: v for k, v in base.items()})


def test_dev_mode_skips_validation():
    """app_env='dev' (default) → eksik secret'lar bile fırlatmaz."""
    s = Settings(APP_ENV="dev", API_AUTH_KEY="")
    s.validate_for_production()  # raise etmez


def test_staging_mode_skips_validation():
    s = Settings(APP_ENV="staging", API_AUTH_KEY="")
    s.validate_for_production()  # raise etmez


def test_prod_passes_with_all_required_set():
    s = _make()
    s.validate_for_production()  # tüm zorunlular set, raise yok


def test_prod_fails_when_api_auth_key_missing():
    s = _make(API_AUTH_KEY="")
    with pytest.raises(ConfigError, match="API_AUTH_KEY"):
        s.validate_for_production()


def test_prod_fails_when_jwt_secret_missing():
    s = _make(JWT_SECRET_KEY="")
    with pytest.raises(ConfigError, match="JWT_SECRET_KEY"):
        s.validate_for_production()


def test_prod_fails_when_database_is_sqlite():
    s = _make(DATABASE_URL="sqlite:///./dev.db")
    with pytest.raises(ConfigError, match="DATABASE_URL"):
        s.validate_for_production()


def test_prod_fails_when_use_fixtures_true():
    s = _make(USE_FIXTURES=True)
    with pytest.raises(ConfigError, match="USE_FIXTURES"):
        s.validate_for_production()


def test_prod_fails_when_api_football_key_missing():
    s = _make(API_FOOTBALL_KEY="")
    with pytest.raises(ConfigError, match="API_FOOTBALL_KEY"):
        s.validate_for_production()


def test_prod_fails_when_backward_compat_api_key_set():
    s = _make(BACKWARD_COMPAT_API_KEY="legacy-key")
    with pytest.raises(ConfigError, match="BACKWARD_COMPAT_API_KEY"):
        s.validate_for_production()


def test_prod_allows_backward_compat_when_explicitly_enabled():
    s = _make(
        BACKWARD_COMPAT_API_KEY="legacy-key",
        ALLOW_BACKWARD_COMPAT_API_KEY=True,
    )
    s.validate_for_production()  # bilinçli açıldı → raise yok


def test_dev_mode_ignores_backward_compat_api_key():
    s = Settings(APP_ENV="dev", BACKWARD_COMPAT_API_KEY="legacy-key")
    s.validate_for_production()  # dev → kontrol yok


def test_prod_reports_all_issues_at_once():
    """Birden çok eksik varsa hepsi tek mesajda görünmeli."""
    s = _make(API_AUTH_KEY="", DATABASE_URL="sqlite:///x.db", USE_FIXTURES=True)
    with pytest.raises(ConfigError) as exc:
        s.validate_for_production()
    msg = str(exc.value)
    assert "API_AUTH_KEY" in msg
    assert "DATABASE_URL" in msg
    assert "USE_FIXTURES" in msg
