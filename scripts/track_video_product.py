"""Ürün işçisi: `scripts.track_video` + ürün yoluna özgü iki davranış (venv-cv).

Argümanlar `scripts.track_video` ile aynıdır. Farklar:
- tekrar süzgeci eskiyen referansı yeniden öğrenir (`app/tracking/replay_relearn.py`);
- sabit kamerada ve kalibrasyon verilmişken sahayı görmeyen dilim pencereleri işlenmez
  (`app/tracking/pitch_windows.py`).

`scripts.track_video` ve `pipeline.py` dondurulmuş ölçüm kodu olduğu için bunlar oraya yazılmadı.
"""
from __future__ import annotations

import argparse
import sys

from app.tracking.replay_relearn import install as install_replay_relearn
from scripts.track_video import main


def static_calibration_path(argv: list[str]) -> str | None:
    """Saha dışı pencere atlamanın uygulanacağı kalibrasyon; koşul sağlanmıyorsa None.

    İşçinin kendi kararını tekrarlar (`scripts.track_video.main`): kamera elle `static` verilmişse
    ya da `auto` iken video sabit bulunursa ve kare başına kalibrasyon zorlanmamışsa uygulanır.
    """
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--video")
    p.add_argument("--calibration", default=None)
    p.add_argument("--camera", default="auto")
    p.add_argument("--per-frame-calibration", default="auto")
    known, _ = p.parse_known_args(argv)
    if not known.video or not known.calibration or known.per_frame_calibration == "on":
        return None
    if known.camera == "static":
        return str(known.calibration)
    if known.camera != "auto":
        return None
    from app.tracking.camera import STATIC_SOURCE, analyze_video

    return str(known.calibration) if analyze_video(known.video).source_name == STATIC_SOURCE else None


if __name__ == "__main__":
    install_replay_relearn()
    calibration_path = static_calibration_path(sys.argv[1:])
    if calibration_path is not None:
        from app.tracking.calibration import PitchCalibration
        from app.tracking.pitch_windows import install as install_pitch_windows

        install_pitch_windows(PitchCalibration.load(calibration_path))
    raise SystemExit(main())
