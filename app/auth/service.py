"""Auth service — login, refresh, logout, register.

Tüm fonksiyonlar Session alır (FastAPI dep'siyle uyumlu). Domain hata
hiyerarşisi: AuthError > InvalidCredentials, TokenExpired, UserExists.
"""

from __future__ import annotations

import hashlib
import uuid as _uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.jwt_tokens import create_access_token, create_refresh_token_value
from app.auth.passwords import hash_password, verify_password
from app.core.config import get_settings
from app.db import models


class AuthError(Exception):
    """Auth domain hatası taban sınıfı."""


class InvalidCredentials(AuthError):
    """Yanlış email/password ya da kullanıcı pasif."""


class TokenExpired(AuthError):
    """Refresh token süresi dolmuş ya da revoke edilmiş."""


class UserExists(AuthError):
    """Aynı (tenant, email) için kullanıcı zaten var."""


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


def _hash_refresh(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_user(
    session: Session, *,
    tenant_id: str, email: str, password: str, role: str,
    user_id: str | None = None,
) -> models.User:
    """Yeni kullanıcı oluştur. (tenant_id, email) duplicate → UserExists.

    role: admin | analyst | coach | viewer (validate'i caller yapar)
    """
    if role not in ("admin", "analyst", "coach", "viewer"):
        raise ValueError(f"role geçersiz: {role}")
    existing = session.execute(
        select(models.User).where(
            models.User.tenant_id == tenant_id,
            models.User.email == email,
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise UserExists(f"user already exists: {email} in tenant {tenant_id}")
    now = datetime.now(UTC)
    user = models.User(
        id=user_id or str(_uuid.uuid4()),
        tenant_id=tenant_id, email=email,
        password_hash=hash_password(password),
        role=role, active=True, created_at=now,
    )
    session.add(user)
    session.flush()
    return user


def login(
    session: Session, *,
    email: str, password: str,
    user_agent: str | None = None, ip: str | None = None,
    tenant_slug: str | None = None,
) -> TokenPair:
    """Email + password → TokenPair (access + refresh).

    Multi-tenant: aynı email farklı tenant'larda olabilir. `tenant_slug`
    verilmezse default tenant'ı dener; verilirse o slug'a karşılık gelen
    tenant içinde arar.
    """
    if tenant_slug:
        tenant = session.execute(
            select(models.Tenant).where(models.Tenant.slug == tenant_slug)
        ).scalar_one_or_none()
        if tenant is None or not tenant.active:
            raise InvalidCredentials("invalid credentials")
        users = session.execute(
            select(models.User).where(
                models.User.tenant_id == tenant.id,
                models.User.email == email,
            )
        ).scalars().all()
    else:
        users = session.execute(
            select(models.User).where(models.User.email == email)
        ).scalars().all()

    # Sabit zamanlı: tüm eşleşen user'ları dene; hiçbiri verify etmezse fail.
    valid_user: models.User | None = None
    for user in users:
        if user.active and verify_password(password, user.password_hash):
            valid_user = user
            break
    if valid_user is None:
        raise InvalidCredentials("invalid credentials")

    # last_login_at update
    valid_user.last_login_at = datetime.now(UTC)

    access = create_access_token(
        user_id=valid_user.id,
        tenant_id=valid_user.tenant_id, role=valid_user.role,
    )
    refresh_raw = create_refresh_token_value()
    s = get_settings()
    refresh_row = models.RefreshToken(
        user_id=valid_user.id,
        token_hash=_hash_refresh(refresh_raw),
        expires_at=datetime.now(UTC) + timedelta(days=s.jwt_refresh_days),
        user_agent=user_agent, ip=ip,
        created_at=datetime.now(UTC),
    )
    session.add(refresh_row)
    session.flush()
    return TokenPair(access_token=access, refresh_token=refresh_raw)


def refresh_access(
    session: Session, *, refresh_token: str,
    user_agent: str | None = None, ip: str | None = None,
) -> TokenPair:
    """Refresh token → yeni access + yeni refresh (rotation: eski revoke).

    Token rotation güvenlik: aynı refresh ile ikinci kez gelinirse eski
    revoke edilmiş hâlde olduğu için 401.
    """
    token_hash = _hash_refresh(refresh_token)
    row = session.execute(
        select(models.RefreshToken).where(
            models.RefreshToken.token_hash == token_hash,
        )
    ).scalar_one_or_none()
    if row is None:
        raise TokenExpired("refresh token not found")
    if row.revoked_at is not None:
        raise TokenExpired("refresh token revoked (suspected replay)")
    now = datetime.now(UTC)
    # SQLite tz-strip uyumu için cmp UTC ile
    if row.expires_at.tzinfo is None:
        cmp_exp = row.expires_at.replace(tzinfo=UTC)
    else:
        cmp_exp = row.expires_at
    if cmp_exp < now:
        raise TokenExpired("refresh token expired")

    user = session.get(models.User, row.user_id)
    if user is None or not user.active:
        raise InvalidCredentials("user inactive")

    # Rotate: eskisini revoke et, yeni issue
    row.revoked_at = now
    new_access = create_access_token(
        user_id=user.id, tenant_id=user.tenant_id, role=user.role,
    )
    new_refresh_raw = create_refresh_token_value()
    s = get_settings()
    new_row = models.RefreshToken(
        user_id=user.id,
        token_hash=_hash_refresh(new_refresh_raw),
        expires_at=now + timedelta(days=s.jwt_refresh_days),
        user_agent=user_agent, ip=ip, created_at=now,
    )
    session.add(new_row)
    session.flush()
    return TokenPair(access_token=new_access, refresh_token=new_refresh_raw)


def logout(session: Session, *, refresh_token: str) -> bool:
    """Refresh token revoke (logout). Yoksa False döner (idempotent)."""
    token_hash = _hash_refresh(refresh_token)
    row = session.execute(
        select(models.RefreshToken).where(
            models.RefreshToken.token_hash == token_hash,
        )
    ).scalar_one_or_none()
    if row is None or row.revoked_at is not None:
        return False
    row.revoked_at = datetime.now(UTC)
    session.flush()
    return True
