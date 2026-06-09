"""SessionLoad — oyuncuya ait günlük antrenman/maç yükü kaydı (AU).

Her kayıt bir seansın iç-yükünü (AU) tutar; kaynak `source` ile etiketlenir:
- "srpe"    → Foster sRPE (RPE × süre), donanımsız evrensel yöntem
- "gps"     → GPS/wearable (Catapult/STATSports → compute_gps_load.session_load)
- "minutes" → maç dakikası proxy

Kaynaktan bağımsız tek seri: bu kayıtlar günlük yük serisine toplanıp
`engine.workload.compute_workload` ile ACWR'ye çevrilir → Hazırlık Kararı.

NOT (mimari): `app/db/physical_test.py` ile aynı desen — proje ORM modelleri
tek `models.py`'de toplanır ama "yalnız yeni dosya ekle" kısıtı gereği ayrı
tutulur. `Base` aynı declarative base; tablo router import edilince
`Base.metadata`'ya kaydolur, Alembic 0025 ile oluşturulur. Tenant izolasyonu
router katmanında manuel `tenant_id` filtresiyle.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import DateTime, Date, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SessionLoad(Base):
    __tablename__ = "session_loads"
    __table_args__ = (
        Index("ix_sl_tenant_player", "tenant_id", "player_id"),
        Index("ix_sl_tenant_date", "tenant_id", "session_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True,
    )
    player_id: Mapped[str] = mapped_column(String(64), index=True)
    player_name: Mapped[str] = mapped_column(String(128))
    session_date: Mapped[date] = mapped_column(Date)
    source: Mapped[str] = mapped_column(String(16))   # "srpe" | "gps" | "minutes"
    load_au: Mapped[float] = mapped_column(Float)      # iç-yük (AU) — ACWR serisine
    rpe: Mapped[float | None] = mapped_column(Float, nullable=True)          # sRPE: 1-10
    duration_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
