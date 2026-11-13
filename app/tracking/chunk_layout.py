"""Parçalı video işlemenin dosya düzeni: işçi sarmalayıcısı yazar, iş ucu koşu sırasında okur.

İki taraf ayrı süreçlerdedir (venv-cv işçisi ve API); ortak bildikleri tek şey bu adlardır.
"""
from __future__ import annotations

from pathlib import Path

# Biten parçanın çıktısı. İşçi çıkışından sonra tek adımda bu ada taşınır; bu adı gören okuyucu
# dosyanın tam yazıldığına güvenebilir.
READY_PREFIX = "ready_"
# Kaç parça işleneceği: {"chunks_total": N}.
PLAN_FILE = "plan.json"


def chunk_dir(out: str | Path) -> Path:
    """Bir işin çıktı JSON yolundan parça klasörü."""
    out = Path(out)
    return out.with_suffix("").with_name(out.stem + "_chunks")
