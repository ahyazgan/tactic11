"""PerformanceTarget — oyuncu/protokol bazlı hedef değer (hedef takibi).

Antrenör "Rıdvan CMJ 55 cm'e çıksın (Ağustos sonu)" der; ilerleme oyuncunun
PhysicalTest geçmişinden (development_curve eğimi) türetilir, burada saklanmaz.

NOT (mimari): `app/db/physical_test.py` / `wellness_entry.py` ile aynı desen —
ayrı dosya, aynı `Base`, router import edilince `Base.metadata`'ya kaydolur,
Alembic 0032 ile oluşturulur. Tenant izolasyonu router katmanında.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PerformanceTarget(Base):
    __tablename__ = "performance_targets"
    __table_args__ = (
        Index("ix_ptarget_tenant_player", "tenant_id", "player_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True,
    )
    player_id: Mapped[str] = mapped_column(String(64), index=True)
    player_name: Mapped[str] = mapped_column(String(128))
    protocol: Mapped[str] = mapped_column(String(32))
    target_value: Mapped[float] = mapped_column(Float)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
