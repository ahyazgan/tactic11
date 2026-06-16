"""WellnessEntry — oyuncunun öznel günlük hazırlık anketi (5 madde, 1-7).

Uyku/yorgunluk/kas ağrısı/stres/ruh hali → readiness skoru (compute_wellness).
ACWR (objektif yük) ile birlikte Hazırlık Kararı'nın öznel yarısını besler.

NOT (mimari): `app/db/physical_test.py` / `session_load.py` ile aynı desen —
ayrı dosya, `Base` aynı declarative base, tablo router import edilince
`Base.metadata`'ya kaydolur, Alembic 0026 ile oluşturulur. Tenant izolasyonu
router katmanında manuel `tenant_id` filtresiyle.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import DateTime, Date, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WellnessEntry(Base):
    __tablename__ = "wellness_entries"
    __table_args__ = (
        Index("ix_we_tenant_player", "tenant_id", "player_id"),
        Index("ix_we_tenant_date", "tenant_id", "entry_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True,
    )
    player_id: Mapped[str] = mapped_column(String(64), index=True)
    player_name: Mapped[str] = mapped_column(String(128))
    entry_date: Mapped[date] = mapped_column(Date)
    sleep_quality: Mapped[int] = mapped_column(Integer)   # 1-7
    fatigue: Mapped[int] = mapped_column(Integer)         # 1-7 (7 = dinç)
    muscle_soreness: Mapped[int] = mapped_column(Integer)  # 1-7 (7 = ağrısız)
    stress: Mapped[int] = mapped_column(Integer)          # 1-7 (7 = sakin)
    mood: Mapped[int] = mapped_column(Integer)            # 1-7
    readiness: Mapped[float] = mapped_column(Float)        # 0..1 (denormalize, gösterim)
    recorded_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
