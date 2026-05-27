"""Test fikstürleri: izole, in-memory SQLite oturumu."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import models  # noqa: F401  Base.metadata'yı doldurur
from app.db.base import Base


@pytest.fixture()
def session() -> Session:
    # StaticPool + check_same_thread=False: TestClient farklı thread'den de
    # aynı in-memory DB'ye ulaşsın.
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionTest = sessionmaker(bind=engine, autoflush=True, expire_on_commit=False, future=True)
    s = SessionTest()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()
