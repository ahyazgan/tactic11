"""SQLAlchemy ORM modelleri.

Tablolar domain modelleriyle bire bir eşleşir; çevirme `data/ingest/` katmanında
yapılır. `tenant_id` bugün yok ama indeks tasarımı sonradan eklemeyi kolaylaştıracak
şekilde basit.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Index, Integer, PrimaryKeyConstraint, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class League(Base):
    __tablename__ = "leagues"
    __table_args__ = (
        UniqueConstraint("sport", "external_id", "season", name="uq_leagues_sport_extid_season"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sport: Mapped[str] = mapped_column(String(32), index=True)
    external_id: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(255))
    season: Mapped[int] = mapped_column(Integer, index=True)
    country: Mapped[str | None] = mapped_column(String(128), nullable=True)


class Team(Base):
    __tablename__ = "teams"
    __table_args__ = (
        UniqueConstraint("sport", "external_id", name="uq_teams_sport_extid"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sport: Mapped[str] = mapped_column(String(32), index=True)
    external_id: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(255))
    country: Mapped[str | None] = mapped_column(String(128), nullable=True)
    founded: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Player(Base):
    __tablename__ = "players"
    __table_args__ = (
        UniqueConstraint("sport", "external_id", name="uq_players_sport_extid"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sport: Mapped[str] = mapped_column(String(32), index=True)
    external_id: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(255))
    position: Mapped[str | None] = mapped_column(String(8), nullable=True)
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    nationality: Mapped[str | None] = mapped_column(String(128), nullable=True)


class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (
        UniqueConstraint("sport", "external_id", name="uq_matches_sport_extid"),
        Index("ix_matches_league_season", "league_external_id", "season"),
        Index("ix_matches_kickoff", "kickoff"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sport: Mapped[str] = mapped_column(String(32), index=True)
    external_id: Mapped[int] = mapped_column(Integer, index=True)
    league_external_id: Mapped[int] = mapped_column(Integer)
    season: Mapped[int] = mapped_column(Integer)
    kickoff: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(8))
    home_team_external_id: Mapped[int] = mapped_column(Integer)
    away_team_external_id: Mapped[int] = mapped_column(Integer)
    home_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_score: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Snapshot(Base):
    """Bir sync sonunda durumun fotoğrafı.

    Üzerine yazılmaz; her sync yeni satır ekler. `scope` örn:
    `"league:203:season:2024"`.
    """

    __tablename__ = "snapshots"
    __table_args__ = (
        Index("ix_snapshots_sport_scope_created", "sport", "scope", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sport: Mapped[str] = mapped_column(String(32))
    scope: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    leagues_count: Mapped[int] = mapped_column(Integer)
    teams_count: Mapped[int] = mapped_column(Integer)
    matches_count: Mapped[int] = mapped_column(Integer)


class UsageEvent(Base):
    """Her dış servis çağrısı için bir kayıt (kota koruması ve maliyet izleme)."""

    __tablename__ = "usage_events"
    __table_args__ = (
        Index("ix_usage_events_source_created", "source", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(64))
    endpoint: Mapped[str] = mapped_column(String(255))
    tokens: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CacheEntry(Base):
    """Adapter yanıtları için TTL'li cache satırı."""

    __tablename__ = "cache_entries"
    __table_args__ = (
        PrimaryKeyConstraint("source", "key", name="pk_cache_entries"),
        Index("ix_cache_entries_expires", "expires_at"),
    )

    source: Mapped[str] = mapped_column(String(64))
    key: Mapped[str] = mapped_column(String(512))
    value: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
