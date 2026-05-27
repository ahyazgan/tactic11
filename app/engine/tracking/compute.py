"""Tracking analiz fonksiyonları — [BOŞ İSKELET, Faz 6'da doldurulacak].

Beklenen üretimler:
- Formation çıkarımı (kümeleme ile 4-3-3 / 4-2-3-1 vb.)
- Pres yoğunluğu (top sahibine yakın rakip oyuncu sayısı / sürede)
- Defansif blok yüksekliği (savunma hattının ortalama x)
- Tracking-tabanlı oyuncu yükü (kat edilen mesafe, sprint sayısı)

Engine kuralı tracking için de geçerli: girdi `Iterable[TrackingFrame]`,
çıktı `EngineResult[T]`. DB/HTTP/LLM yok.

Bugün stub: TypeError ile çağıranı uyarır, sözleşmeyi netleştirir.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.audit import EngineResult
from app.domain import TrackingFrame

ENGINE_NAME = "engine.tracking"
ENGINE_VERSION = "0"  # 0 = stub; gerçek implementasyon v1'de gelir


def compute_pressure(
    team_external_id: int,
    frames: Iterable[TrackingFrame],
) -> EngineResult:
    """Top sahibi rakip çevresindeki bu takımın pres yoğunluğu."""
    raise NotImplementedError(
        "engine.tracking Faz 6'da doldurulacak; önce TrackingDataSource adapter'ı + "
        "ingest gerek."
    )


def compute_formation(
    team_external_id: int,
    frames: Iterable[TrackingFrame],
) -> EngineResult:
    """Kümeleme ile yerleşim çıkarımı (örn. '4-3-3', '4-2-3-1')."""
    raise NotImplementedError(
        "engine.tracking Faz 6'da doldurulacak; önce TrackingDataSource adapter'ı + "
        "ingest gerek."
    )
