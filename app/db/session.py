"""SQLAlchemy engine ve session yönetimi."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

_settings = get_settings()


def _normalize_db_url(url: str) -> str:
    """Render/Heroku tarzı `postgres://`/`postgresql://` URL'lerini uygulamanın
    psycopg v3 sürücüsüne (`postgresql+psycopg://`) çevir. `+driver` zaten varsa
    dokunma. Deploy taşınabilirliği için."""
    if url.startswith("postgresql+"):
        return url
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    return url


_db_url = _normalize_db_url(_settings.database_url)

# Pool ayarları yük altında bağlantı yetmezliğini ve kopuk uzun bağlantıları
# önler. SQLite (test/dev) QueuePool kullanmaz → pool_size vb. uygulanmaz.
_engine_kwargs: dict = {"pool_pre_ping": True, "future": True}
if not _db_url.startswith("sqlite"):
    _engine_kwargs.update(
        pool_size=_settings.db_pool_size,
        max_overflow=_settings.db_max_overflow,
        pool_recycle=_settings.db_pool_recycle_seconds,
    )

engine = create_engine(_db_url, **_engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=True, expire_on_commit=False, future=True)

# Tenant filter — global Session listener (loader_criteria + before_flush
# auto-fill). Burada import + install: SessionLocal'ı kullanan tüm yollar
# (FastAPI, scheduler jobs, scripts) otomatik tenant-aware.
from app.db.tenant_filter import install_tenant_filter  # noqa: E402

install_tenant_filter()


def get_session() -> Iterator[Session]:
    """FastAPI dependency / context yardımcısı."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
