"""Ürün işçisi: ayak noktası saha çizgilerinin dışına düşen kişileri kareye yazmaz (venv-cv).

Neden ayrı modül: `app/tracking/pipeline.py` kör kontroller için hash'le dondurulmuş ölçüm
kodudur ve `frames.build_frame`'i kendi ad alanına alır. Ürün işçisi
(`scripts/track_video_product.py`) çalışırken `install()` bu adı yeniden bağlar; ölçüm
betikleri ve canlı yol eski kuralla çalışmayı sürdürür.

Düzelttiği kusur: `build_frame` 2 m payla saha dışını kabul edip konumu 0..100'e kırpar.
Yedekler, görevliler ve top toplayıcılar çizgiye yapışıp oyuncu sayılır. Ölçüldü (132877
1800-2100): çizgideki 4175 işaretin %99,8'i gerçek oyuncuya eşleşmedi, kesinlik %67,9
(docs/measurements/product-excess-markers-132877.json). Görülmemiş pencerede ön kayıtlı
sınav: docs/measurements/off-pitch-drop-132877-2100-preregistration.json.
"""
from __future__ import annotations

from typing import Any

from app.tracking.frames import build_frame

# Çizginin dışı saha dışıdır; ayarlanmadı.
PLAYER_MARGIN_M = 0.0


def build_frame_inside_lines(*, calib: Any, players: list[Any], **kwargs: Any) -> Any:
    """`build_frame`, ama yalnız ayak noktası çizgilerin içinde kalan oyuncu gözlemleriyle."""
    inside = [obs for obs in players if calib.is_on_pitch(obs.u, obs.v, margin_m=PLAYER_MARGIN_M)]
    return build_frame(calib=calib, players=inside, **kwargs)


def install() -> None:
    """Bu süreçte `pipeline`'ın kare kurucusunu çizgi içi sürümle değiştirir."""
    from app.tracking import pipeline

    setattr(pipeline, "build_frame", build_frame_inside_lines)  # noqa: B010 — dondurulmuş modülde ad yeniden bağlanır
