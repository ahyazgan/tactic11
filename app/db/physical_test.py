"""PhysicalTest — oyuncuya ait saha performans testi kaydı.

Her kayıt bir test oturumuna (tarih + protokol) karşılık gelir.

NOT (mimari): Proje ORM modelleri tek dosyada (``app/db/models.py``) toplanıyor;
bu modül "yalnız yeni dosya ekle" kısıtı gereği ayrı tutuldu (``app/db/models/``
paketi açmak ``from app.db import models`` importunu gölgeleyip kırardı). ``Base``
aynı declarative base. Tablo, router import edildiğinde ``Base.metadata``'ya
kaydolur ve Alembic 0022 migration'ı ile oluşturulur. Tenant izolasyonu router
katmanında manuel ``tenant_id`` filtresiyle sağlanır — model ``_TENANT_MODELS``'e
eklenmediği için otomatik filtre/autofill kapsamı dışındadır (tenant_filter.py'ye
dokunulmaz).
"""

from __future__ import annotations

import enum
from datetime import date

from typing import Any

from sqlalchemy import JSON, Date, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TestProtocol(enum.StrEnum):
    """Desteklenen saha test protokolleri (değer = DB'de saklanan string)."""

    SPRINT_10M = "sprint_10m"        # sn
    SPRINT_30M = "sprint_30m"        # sn
    TTEST_AGILITY = "ttest_agility"  # sn — T-test çeviklik
    RSA = "rsa"                      # sn — tekrarlı sprint ortalaması
    YOYO_IRL1 = "yoyo_irl1"          # seviye (örn: 17.4)
    YOYO_IRL2 = "yoyo_irl2"
    CMJ = "cmj"                      # countermovement jump — cm
    SJ = "sj"                        # squat jump — cm
    ISOKINETIC_Q = "isokinetic_quad"  # Nm/kg
    ISOKINETIC_H = "isokinetic_ham"   # Nm/kg
    VO2MAX = "vo2max"                # ml/kg/min (Cooper/Beep)
    GPS_DISTANCE = "gps_total_dist"  # metre (maç/antrenman)
    GPS_HIRD = "gps_hir_dist"        # high-intensity running distance
    GPS_ACC = "gps_acc_count"        # atak sayısı
    BODY_FAT = "body_fat_pct"        # %
    # Faz 2 ek protokolleri (sürat split / çeviklik / patlayıcı / MD+1).
    SPRINT_5M = "sprint_5m"          # sn — 5m reaksiyon/ilk adım
    T505 = "t505"                    # sn — 505 yön değiştirme
    ARROWHEAD = "arrowhead"          # sn — arrowhead çeviklik
    ILLINOIS = "illinois"            # sn — illinois çeviklik
    IFT_30_15 = "ift_30_15"          # km/sa — VIFT
    ADDUCTOR_SQUEEZE = "adductor_squeeze"  # N — kasık kuvveti (MD+1)
    DROP_JUMP_RSI = "drop_jump_rsi"  # RSI — reaktif kuvvet
    TRIPLE_HOP = "triple_hop"        # cm — tek bacak 3 sıçrama
    CUSTOM = "custom"                # serbest


class PhysicalTest(Base):
    __tablename__ = "physical_tests"
    __table_args__ = (
        Index("ix_pt_tenant_player", "tenant_id", "player_id"),
        Index("ix_pt_tenant_date", "tenant_id", "test_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Multi-tenant zorunlu — diğer modellerle aynı tip + FK + CASCADE.
    tenant_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True,
    )
    player_id: Mapped[str] = mapped_column(String(64), index=True)  # API-Football player_id
    player_name: Mapped[str] = mapped_column(String(128))           # denormalize — hız için
    test_date: Mapped[date] = mapped_column(Date)
    # Protokol string olarak saklanır (ev konvansiyonu: native enum kullanılmaz);
    # geçerli değerler TestProtocol enum'ından gelir, API katmanı doğrular.
    protocol: Mapped[str] = mapped_column(String(32))
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)  # otomatik doldurulur
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_by: Mapped[str | None] = mapped_column(String(128), nullable=True)  # girişi yapan
    # Çok-bileşenli ham veri (saklanır): RSA 6 sprint süresi, Drop Jump uçuş/temas,
    # Triple Hop sol/sağ, COD 505+10m vb. `value` türetilmiş metriği tutar
    # (FI/RSI/asimetri), `components` ham bileşenleri JSON olarak. Nullable.
    components: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
