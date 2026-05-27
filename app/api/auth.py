"""JWT tabanlı multi-tenant auth + endpoints.

İki yol var:
1. **JWT (yeni, üretim)**: `Authorization: Bearer <token>` header. Login ile
   alınır, expired ise /auth/refresh ile yenilenir.
2. **X-API-Key (backward-compat)**: settings.backward_compat_api_key set'liyse
   o key kabul edilir, default tenant + admin user'a map edilir. Eski
   integration'lar kırılmasın diye.

Endpoint'ler:
- POST /auth/login        — email + password (+ optional tenant_slug) → TokenPair
- POST /auth/refresh      — refresh token → yeni TokenPair (rotation)
- POST /auth/logout       — refresh token revoke
- GET  /auth/me           — current user info

Dependencies:
- get_current_user        — JWT/API-key'den User çıkar
- get_current_tenant      — User'dan Tenant döner
- require_role(roles)     — rol kontrolü factory
"""

from __future__ import annotations

from typing import Iterable

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.service import (
    InvalidCredentials,
    TokenExpired,
    login as svc_login,
    logout as svc_logout,
    refresh_access as svc_refresh,
)
from app.auth.jwt_tokens import decode_access_token
from app.core.config import get_settings
from app.core.logging import get_logger
from app.db import models
from app.db.session import get_session
from app.db.tenant_context import DEFAULT_TENANT_ID, set_current_tenant_id

log = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


# --------------------------------------------------------------------------- #
# Pydantic schemas
# --------------------------------------------------------------------------- #


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=1)
    tenant_slug: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class TokenPairResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserMe(BaseModel):
    id: str
    email: str
    role: str
    tenant_id: str
    tenant_slug: str | None = None


# --------------------------------------------------------------------------- #
# Auth endpoints
# --------------------------------------------------------------------------- #


@router.post("/login", response_model=TokenPairResponse)
def login(
    body: LoginRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> TokenPairResponse:
    try:
        ua = request.headers.get("user-agent")
        ip = request.client.host if request.client else None
        pair = svc_login(
            session,
            email=body.email, password=body.password,
            tenant_slug=body.tenant_slug,
            user_agent=ua, ip=ip,
        )
        session.commit()
    except InvalidCredentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid credentials",
        )
    return TokenPairResponse(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
    )


@router.post("/refresh", response_model=TokenPairResponse)
def refresh(
    body: RefreshRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> TokenPairResponse:
    try:
        ua = request.headers.get("user-agent")
        ip = request.client.host if request.client else None
        pair = svc_refresh(
            session, refresh_token=body.refresh_token,
            user_agent=ua, ip=ip,
        )
        session.commit()
    except TokenExpired as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e) or "refresh token invalid",
        )
    except InvalidCredentials as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e) or "invalid credentials",
        )
    return TokenPairResponse(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
    )


@router.post("/logout")
def logout(
    body: LogoutRequest,
    session: Session = Depends(get_session),
) -> dict[str, bool]:
    revoked = svc_logout(session, refresh_token=body.refresh_token)
    session.commit()
    return {"revoked": revoked}


# --------------------------------------------------------------------------- #
# Dependencies — get_current_user / tenant / require_role
# --------------------------------------------------------------------------- #


def _user_from_jwt(
    authorization: str, session: Session,
) -> models.User:
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid auth scheme",
        )
    token = authorization[7:].strip()
    try:
        claims = decode_access_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="access token expired",
        )
    except jwt.PyJWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"invalid access token: {type(e).__name__}",
        )
    user = session.get(models.User, claims.sub)
    if user is None or not user.active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="user not found or inactive",
        )
    return user


def _user_from_legacy_api_key(
    api_key: str, session: Session,
) -> models.User | None:
    """X-API-Key backward compat — `api_auth_key` (eski) ya da
    `backward_compat_api_key` (yeni isim) eşleşirse default tenant'ın
    admin user'ını döner. User DB'de yoksa "no-auth ghost user" döner
    (in-memory; tenant_id default — eski testler için).
    """
    import secrets as _s
    s = get_settings()
    expected_keys = [k for k in (s.api_auth_key, s.backward_compat_api_key) if k]
    if not expected_keys:
        return None
    if not any(_s.compare_digest(api_key, k) for k in expected_keys):
        return None
    # Default tenant'ın admin user'ı — yoksa "ghost" user (testler için)
    user = session.execute(
        select(models.User).where(
            models.User.tenant_id == DEFAULT_TENANT_ID,
            models.User.role == "admin",
        ).limit(1)
    ).scalar_one_or_none()
    if user is not None:
        return user
    # Test DB'sinde users yoktur → in-memory ghost (tenant filter pasif kalır)
    ghost = models.User(
        id="legacy-api-key-ghost",
        tenant_id=DEFAULT_TENANT_ID,
        email="legacy@api-key",
        password_hash="",
        role="admin", active=True,
    )
    return ghost


def _apply_user_context(
    request: Request, session: Session, user: models.User,
) -> None:
    """User resolve edildi — tenant_id'yi session.info ve ContextVar'a yaz.

    `session.info` request-scoped (FastAPI session her request'te yeni
    instance); tenant_filter listener bunu okur. ContextVar de ayrıca
    set'lenir ama threadpool context copy nedeniyle güvenilmez — info dict
    asıl kaynak.
    """
    request.state.current_user_id = user.id
    request.state.current_tenant_id = user.tenant_id
    session.info["tenant_id"] = user.tenant_id
    set_current_tenant_id(user.tenant_id)


def get_current_user(
    request: Request,
    session: Session = Depends(get_session),
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> models.User:
    """JWT bearer veya X-API-Key — sırasıyla dene; ikisi de fail ise 401."""
    if authorization:
        user = _user_from_jwt(authorization, session)
        _apply_user_context(request, session, user)
        return user
    if x_api_key:
        user = _user_from_legacy_api_key(x_api_key, session)
        if user is not None:
            _apply_user_context(request, session, user)
            return user
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="authentication required",
    )


def get_current_tenant(
    user: models.User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> models.Tenant:
    tenant = session.get(models.Tenant, user.tenant_id)
    if tenant is None or not tenant.active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="tenant inactive",
        )
    return tenant


def require_role(roles: Iterable[str]):
    """Dependency factory — kullanıcı role'ü `roles` içinde olmalı."""
    allowed = set(roles)

    def _guard(user: models.User = Depends(get_current_user)) -> models.User:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"role '{user.role}' not allowed (need: {sorted(allowed)})",
            )
        return user

    return _guard


# --------------------------------------------------------------------------- #
# /auth/me (current user)
# --------------------------------------------------------------------------- #


@router.get("/me", response_model=UserMe)
def me(
    user: models.User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> UserMe:
    tenant = session.get(models.Tenant, user.tenant_id)
    return UserMe(
        id=user.id, email=user.email, role=user.role,
        tenant_id=user.tenant_id,
        tenant_slug=tenant.slug if tenant is not None else None,
    )


# --------------------------------------------------------------------------- #
# Backward-compat — eski `require_api_key` adı protected router için
# --------------------------------------------------------------------------- #


def require_api_key(
    request: Request,
    session: Session = Depends(get_session),
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> models.User | None:
    """Backward-compat dependency. İki davranış modu:

    A) `api_auth_key` boş VE `backward_compat_api_key` boş VE JWT yok →
       AUTH DEVRE DIŞI (eski test/dev davranışı). None döner, tenant filter
       de pasif (current_tenant_id set'lenmiyor) — eski testler değişmeden geçer.

    B) Yukarıdakilerden biri set'liyse → JWT/legacy-key resolve et,
       set_current_tenant_id'i çağır, User döndür. Eski endpoint kodu
       genelde dönüş değerini kullanmıyor (sadece guard); yine de
       backward-compat.
    """
    s = get_settings()
    no_auth_configured = (
        not s.api_auth_key
        and not s.backward_compat_api_key
        and not s.jwt_secret_key
    )
    if no_auth_configured and not authorization and not x_api_key:
        # Dev/test "auth disabled" modu — eski semantik
        return None

    # En azından bir şey var: JWT bearer veya x_api_key — resolve et
    return get_current_user(
        request=request, session=session,
        authorization=authorization, x_api_key=x_api_key,
    )
