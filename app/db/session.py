"""SQLAlchemy engine ve session yönetimi."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

engine = create_engine(get_settings().database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=True, expire_on_commit=False, future=True)


def get_session() -> Iterator[Session]:
    """FastAPI dependency / context yardımcısı."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
