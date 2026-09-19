"""MatchLoadSample — maç İÇİNDE, dakika çözünürlüklü oyuncu yükü.

## Neden ayrı bir tablo

`session_loads` bir SEANSIN toplam iç-yükünü tutar (günlük seri → ACWR →
sakatlık riski). "62. dakikada bu oyuncu ne kadar koştu" sorusunu cevaplayamaz,
çünkü tek satır tüm maçtır.

Maç-içi karar bu ayrıntıyı ister. Karnenin ölçtüğü tek zayıflık grup İÇİNDE
kimin çıkacağıdır: motor doğru mevki grubunu buluyor, grubun içinden doğru
kişiyi bulamıyor. Olay verisinden türetilen altı sinyal (pas isabeti, dokunuş
düşüşü, müdahale sayısı…) iki yönde de sınandı ve hiçbiri rastgeleyi geçmedi —
ayrık yarıda kazanç +0,001, permütasyon p = 0,62
(`docs/KARNE-GRUP-ICI-SINYAL.md`). O yön kapandı; gereken şey **başka bir veri
türü**: gerçek koşu yükü.

## Kaynak

- **GPS/giyilebilir** (Catapult, STATSports, WIMU): birincil kaynak. Cihaz
  maç boyunca örnek üretir; bu tablo örnekleri KÜMÜLATİF olarak tutar.
- **Takipten türetme**: video takibi de konum üretir, dolayısıyla mesafe
  hesaplanabilir. Ama oyuncu kimliği elle eşlenmek zorunda ve takım ataması
  şu an %80 civarı; bu yolla gelen yük `source="tracking"` ile etiketlenir ve
  GPS'le aynı güvende sayılmaz.

## Kümülatif, anlık değil

Her satır "maç başından bu dakikaya kadar" toplamdır. Nedeni: karar anı
keyfîdir (66. dakikada soruluyorsa 66'ya kadarki yük istenir) ve kümülatif
seriden herhangi iki dakika arasındaki fark çıkarılabilir; tersi mümkün değil.

## Ölçülmeden kullanılmaz

Bu tablo veri TAŞIR; öneriye bağlanması ayrı bir karardır ve ancak
`scripts/measure_within_group_signal.py` aynı sertlikte (iki yön, beraberlik
tarafsız, maç bazında ayrık yarı, permütasyon) sınadıktan sonra yapılır.
Ölçülmemiş bir sinyali motora eklemek, tam da bu projede defalarca eleştirilen
şeydir. Ön-kayıtlı sınav planı: `docs/MAC-ICI-YUK-PLANI.md`.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MatchLoadSample(Base):
    __tablename__ = "match_load_samples"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "match_external_id", "player_external_id", "minute",
            name="uq_match_load_player_minute",
        ),
        Index("ix_mls_match_minute", "match_external_id", "minute"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True,
    )
    match_external_id: Mapped[int] = mapped_column(Integer, index=True)
    player_external_id: Mapped[int] = mapped_column(BigInteger, index=True)
    team_external_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Maç saati. Kümülatif değerler "maç başından bu dakikaya" kadardır.
    minute: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(16))   # "gps" | "tracking"

    total_distance_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Yüksek hız koşusu ve sprint eşikleri kulüpten kulüba değişir; hangi eşiğin
    # kullanıldığı `speed_thresholds` ile birlikte yazılır, yoksa kıyas yanlış olur.
    high_speed_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    sprint_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    accelerations: Mapped[int | None] = mapped_column(Integer, nullable=True)
    decelerations: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Cihazın kendi bileşik yükü (varsa) — türetmeye tercih edilir.
    device_load_au: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_speed_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    speed_thresholds: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
