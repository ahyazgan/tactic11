"""Paylaşılabilir PDF raporu için imzalı kısa token (Faz 5 #40).

JWT yerine dar amaçlı kompakt HMAC token: `{payload_b64}.{sig_b64}`.
Payload `{"o": output_id, "exp": iso_timestamp}` minimal — kısa link
mantığı korunur. Token alıcısı API key olmadan tek bir AgentOutput PDF'e
erişir; expiry geçince 410 döner.

Settings.jwt_secret_key boşsa share devre dışı (endpoint 503).
"""
from __future__ import annotations

import base64
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256

DEFAULT_TTL_HOURS = 24
MAX_TTL_HOURS = 24 * 30  # 30 gün üst sınır


class ShareTokenError(Exception):
    """Token format / signature / expiry hataları için base."""


class ShareTokenInvalid(ShareTokenError):
    """Imza eşleşmiyor veya format bozuk."""


class ShareTokenExpired(ShareTokenError):
    """exp dolmuş."""


@dataclass(frozen=True)
class ShareTokenPayload:
    output_id: int
    expires_at: datetime


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    padded = s + "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _sign(payload_b64: str, secret: str) -> str:
    mac = hmac.new(
        secret.encode("utf-8"),
        payload_b64.encode("ascii"),
        sha256,
    ).digest()
    return _b64url_encode(mac)


def encode_share_token(
    output_id: int,
    *,
    secret: str,
    ttl_hours: int = DEFAULT_TTL_HOURS,
    now: datetime | None = None,
) -> str:
    """Bir AgentOutput id'si için imzalı kısa share token üret."""
    if not secret:
        raise ShareTokenError("secret boş — JWT_SECRET_KEY set'lenmeli")
    if ttl_hours <= 0:
        raise ShareTokenError("ttl_hours > 0 olmalı")
    if ttl_hours > MAX_TTL_HOURS:
        raise ShareTokenError(f"ttl_hours <= {MAX_TTL_HOURS} olmalı")
    base = now or datetime.now(UTC)
    exp = base + timedelta(hours=ttl_hours)
    payload = {"o": int(output_id), "exp": exp.isoformat()}
    payload_b64 = _b64url_encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8"),
    )
    sig = _sign(payload_b64, secret)
    return f"{payload_b64}.{sig}"


def decode_share_token(
    token: str,
    *,
    secret: str,
    now: datetime | None = None,
) -> ShareTokenPayload:
    """Token'ı doğrula + expiry'yi kontrol et + payload döndür."""
    if not secret:
        raise ShareTokenError("secret boş — server tarafı share devre dışı")
    if not token or "." not in token:
        raise ShareTokenInvalid("token format bozuk")
    payload_b64, sig = token.rsplit(".", 1)
    expected_sig = _sign(payload_b64, secret)
    if not hmac.compare_digest(sig, expected_sig):
        raise ShareTokenInvalid("imza eşleşmiyor")
    try:
        payload = json.loads(_b64url_decode(payload_b64))
    except (ValueError, json.JSONDecodeError) as e:
        raise ShareTokenInvalid(f"payload çözülemedi: {e}") from e

    output_id = payload.get("o")
    exp_str = payload.get("exp")
    if not isinstance(output_id, int) or not isinstance(exp_str, str):
        raise ShareTokenInvalid("payload alanları eksik")
    try:
        exp_dt = datetime.fromisoformat(exp_str)
    except ValueError as e:
        raise ShareTokenInvalid(f"exp tarih çözülemedi: {e}") from e
    if exp_dt.tzinfo is None:
        exp_dt = exp_dt.replace(tzinfo=UTC)

    current = now or datetime.now(UTC)
    if current >= exp_dt:
        raise ShareTokenExpired(f"token süresi dolmuş: {exp_str}")

    return ShareTokenPayload(output_id=output_id, expires_at=exp_dt)
