"""Makine kaynağı ölçümü ve video işçisi için başlamadan önce bellek kapısı.

Neden: video işçisi yaklaşık 10 GB ayrılabilir (commit) bellek ister (ölçüm: işçi RSS
2,6 GB / commit 10 GB, 15 dakikalık tanı koşusu, 2026-11-13). Ayrılabilir pay 7,5 GB iken
başlatılan tam maç koşusu 50 dakika çalışıp `ArrayMemoryError` ile öldü ve çıktı vermedi
(`docs/measurements/product-full-match-exam-result-attempt2.json`). Yetmeyecek belleği iş
başlamadan söylemek, 50 dakika sonra çökmekten iyidir.
"""
from __future__ import annotations

import os
import sys

# Ölçülen işçi isteği 10 GB + %10 pay. Başka makinede `TRACKING_MIN_COMMIT_MB` ile
# değiştirilir; 0 kapıyı kapatır.
DEFAULT_MIN_COMMIT_MB = 11_000
# 1080p'den büyük kare (ör. 4096x1080 panorama): 30 dakikalık koşuda ayrılabilir bellek
# 17,6 GB'tan 5,1 GB'a indi, yani işçi yaklaşık 12,5 GB istedi
# (docs/measurements/product-full-match-exam-result-attempt3.json). 12,5 GB + %10 pay.
LARGE_FRAME_PIXELS = 1920 * 1080
LARGE_FRAME_MIN_COMMIT_MB = 14_000
# İşçi sarmalayıcısının "bellek yetmiyor, başlamadım" çıkış kodu; iş ucu bunu sebebe çevirir.
EXIT_MEMORY_SHORT = 5
MIN_COMMIT_ENV = "TRACKING_MIN_COMMIT_MB"


def system_memory_mb() -> dict[str, float] | None:
    """Boş fiziksel bellek ve ayrılabilir (commit) pay; Windows dışında ölçülmez, uydurulmaz."""
    if sys.platform != "win32":
        return None
    import ctypes

    class _Status(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong), *[
            (name, ctypes.c_ulonglong) for name in
            ("total_phys", "avail_phys", "total_commit", "avail_commit", "total_virtual", "avail_virtual", "ext")]]

    status = _Status()
    status.length = ctypes.sizeof(_Status)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return None
    return {"avail_phys_mb": round(status.avail_phys / 1e6), "avail_commit_mb": round(status.avail_commit / 1e6)}


def min_commit_mb(width: int | None = None, height: int | None = None) -> int:
    """İşçinin isteyeceği ayrılabilir bellek; görüntü boyutu biliniyorsa ona göre.

    İki ölçüm noktası var, aradaki boyutlar için tahmin yürütülmez: 1080p'ye kadar 11 GB,
    daha büyük görüntüde `LARGE_FRAME_MIN_COMMIT_MB`. Ortam değişkeni ikisini de ezer.
    """
    raw = os.environ.get(MIN_COMMIT_ENV, "").strip()
    if raw.isdigit():
        return int(raw)
    if width and height and width * height > LARGE_FRAME_PIXELS:
        return LARGE_FRAME_MIN_COMMIT_MB
    return DEFAULT_MIN_COMMIT_MB


def worker_memory_error(memory: dict[str, float] | None, required_mb: int) -> str | None:
    """Bellek işçiye yetmiyorsa kullanıcıya gösterilecek sebep; yetiyorsa ya da ölçülemiyorsa None."""
    if memory is None or required_mb <= 0:
        return None
    available = memory["avail_commit_mb"]
    if available >= required_mb:
        return None
    return (f"bellek yetersiz: video işçisi yaklaşık {required_mb / 1000:.0f} GB ayrılabilir bellek ister, "
            f"şu an {available / 1000:.1f} GB var. Diğer uygulamaları kapatıp işi yeniden başlatın.")
