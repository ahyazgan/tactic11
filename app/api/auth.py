"""API key tabanlı basit auth.

`API_AUTH_KEY` boş ise dev modu: dependency hiçbir şey yapmaz, tüm istekler
geçer. Doluysa istemcinin `X-API-Key` header'ı eşleşmeli; aksi halde 401.

JWT/OAuth ve kullanıcı/rol modeli ileride (multi-tenant ile birlikte) gelir.
Bu katman tek-kulüp / dahili API kullanımı için yeterli.
"""

from __future__ import annotations

import secrets

from fastapi import Header, HTTPException, status

from app.core.config import get_settings


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    expected = get_settings().api_auth_key
    if not expected:
        return  # dev modu — auth devre dışı
    if x_api_key is None or not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or missing X-API-Key",
        )
