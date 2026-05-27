"""JWT token üretimi + doğrulama.

Access token: short-lived (default 15 dakika), claims = {sub, tenant_id, role, exp, iat}
Refresh token: opaque string (UUID-like 64 byte random); DB'de sha256 hash'lendi
ve user_id ile bağlanır. JWT değil — server-side revocable olmalı.

JWT_SECRET_KEY env'den okunur. Production'da boşsa fail-fast — app açılmaz.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import get_settings


@dataclass(frozen=True)
class AccessClaims:
    sub: str  # user_id
    tenant_id: str
    role: str
    exp: datetime
    iat: datetime


_DEV_FALLBACK_SECRET = "manager2-dev-do-not-use-in-prod-32-byte-fallback"


def _secret() -> str:
    s = get_settings()
    if s.jwt_secret_key:
        return s.jwt_secret_key
    if s.app_env == "prod":
        # Production fail-fast Settings.validate_for_production'da yakalanır,
        # buraya gelirse defensive
        raise RuntimeError(
            "JWT_SECRET_KEY tanımlı değil. .env'e ekleyin (32+ byte random)."
        )
    # Dev/test: deterministik fallback (testler reproducible)
    return _DEV_FALLBACK_SECRET


def create_access_token(
    *, user_id: str, tenant_id: str, role: str,
    expires_minutes: int | None = None,
) -> str:
    """HS256 imzalı access token. Default expiry settings.jwt_access_minutes.

    `jti` (JWT ID) claim: cryptographic random — aynı saniyede üretilen
    token'lar farklı olur (refresh rotation testleri için).
    """
    s = get_settings()
    minutes = expires_minutes if expires_minutes is not None else s.jwt_access_minutes
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=minutes)).timestamp()),
        "jti": secrets.token_hex(8),  # unique identifier
    }
    return jwt.encode(payload, _secret(), algorithm="HS256")


def decode_access_token(token: str) -> AccessClaims:
    """Token'i doğrula; expired/invalid → jwt.PyJWTError fırlatır."""
    payload = jwt.decode(token, _secret(), algorithms=["HS256"])
    return AccessClaims(
        sub=str(payload["sub"]),
        tenant_id=str(payload["tenant_id"]),
        role=str(payload["role"]),
        iat=datetime.fromtimestamp(int(payload["iat"]), tz=UTC),
        exp=datetime.fromtimestamp(int(payload["exp"]), tz=UTC),
    )


def create_refresh_token_value() -> str:
    """Opaque refresh token — 64 byte random hex string.

    DB'ye sha256 hash'i yazılır; bu raw değer SADECE bir kez kullanıcıya
    gösterilir. Re-issue ile rotate edilir.
    """
    return secrets.token_hex(32)  # 64 char hex
