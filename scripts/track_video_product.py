"""Ürün işçisi: `scripts.track_video` + ürün yoluna özgü davranışlar (venv-cv).

Argümanlar `scripts.track_video` ile aynıdır, iki fark vardır. `scripts.track_video` ve
`pipeline.py` dondurulmuş ölçüm kodu olduğu için bu davranışlar oraya yazılmadı.

- Tekrar süzgeci eskiyen referansı yeniden öğrenir (`app/tracking/replay_relearn.py`).
- `--broadcast-two-pass`: gündüz TV yayını, yalnız maç sonrası. Video önce iki kez okunur, kamera
  konumu maçın kendisinden bulunur ve duruşlar hatta hazır verilir
  (`app/tracking/broadcast_calibrator.py`). `--camera broadcast` ile birlikte verilir. Yavaştır
  (6 dk'lık kesit ~25 dk). Kamera bulunamazsa çıktı üretilmez (çıkış kodu 2).
"""
from __future__ import annotations

import sys

from app.tracking.broadcast_calibrator import FLAG, two_pass_process_video
from app.tracking.replay_relearn import install
from scripts import track_video


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    install()
    if FLAG in args:
        args.remove(FLAG)
        setattr(track_video, "process_video", two_pass_process_video(track_video.process_video))  # noqa: B010
    sys.argv[1:] = args
    return track_video.main()


if __name__ == "__main__":
    raise SystemExit(main())
