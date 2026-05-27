"""SQLAlchemy declarative base.

`models.py` ve Alembic'in `env.py` bu Base.metadata'yı paylaşır.
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
