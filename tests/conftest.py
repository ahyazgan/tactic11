"""Test fikstürleri: izole, in-memory SQLite oturumu."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import models  # noqa: F401  Base.metadata'yı doldurur
from app.db.base import Base


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    SessionTest = sessionmaker(bind=engine, autoflush=True, expire_on_commit=False, future=True)
    s = SessionTest()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()
