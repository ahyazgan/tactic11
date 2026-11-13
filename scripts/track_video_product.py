"""Ürün işçisi: `scripts.track_video` + ürün yoluna özgü tekrar süzgeci (venv-cv).

Argümanlar `scripts.track_video` ile aynıdır. Fark tek satır: tekrar süzgeci eskiyen
referansı yeniden öğrenir (`app/tracking/replay_relearn.py`). `scripts.track_video` ve
`pipeline.py` dondurulmuş ölçüm kodu olduğu için bu davranış oraya yazılmadı.
"""
from __future__ import annotations

from app.tracking.replay_relearn import install
from scripts.track_video import main

if __name__ == "__main__":
    install()
    raise SystemExit(main())
