"""GSR saha konumlarını saha işareti kalibrasyonuyla yeniden kur (venv-cv).

SoccerTrack GSR tablosunun saha koordinatları resmî saha işaretlerine göre sahanın eni
boyunca birkaç metre sapıyor; piksel ayak noktaları ise panorama uzayında ve doğru
(docs/measurements/gsr-reference-geometry.json). Bu araç `export_gt` çıktısındaki
her satırın saha konumunu (sütun 6–7, merkez sıfırlı metre) ayak pikselini (sütun
4–5) kalibrasyondan geçirerek yeniden yazar; diğer sütunlar değişmez. Piksel
koordinatı panoramanın uzayında değilse `--v-offset` ile kaydırılır (117092: GSR
görüntüsü 3840×1504, panorama 3840×1906).

    venv-cv\\Scripts\\python.exe -X utf8 -m scripts.soccertrack_v2.correct_gsr_positions \\
        --gt data/tracking/bench/gsr_132831_600_1200.npy \\
        --calibration data/tracking/calibrations/soccertrack_v2_132831_landmarks.json \\
        --out data/tracking/bench/gsr_132831_600_1200_corrected.npy
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from app.tracking.calibration import PitchCalibration

CENTRE = np.array([52.5, 34.0])


def correct_positions(rows: np.ndarray, calib: PitchCalibration, *, v_offset: float = 0.0) -> tuple[np.ndarray, dict]:
    """Yeni tablo ve özet; ayak pikseli olmayan satırların konumu NaN olur."""
    out = rows.copy()
    ok = np.isfinite(rows[:, 4:6]).all(axis=1)
    pts = np.array([calib.image_to_pitch_m(u, v + v_offset) for u, v in rows[ok, 4:6]], dtype=float).reshape(-1, 2)
    out[ok, 6:8] = pts - CENTRE
    out[~ok, 6:8] = np.nan
    both = ok & np.isfinite(rows[:, 6:8]).all(axis=1)
    shift = out[both, 6:8] - rows[both, 6:8]
    return out, {"rows": int(len(rows)), "repositioned": int(ok.sum()),
                 "shift_vs_original_m": {"dx_median": round(float(np.median(shift[:, 0])), 2),
                                         "dy_median": round(float(np.median(shift[:, 1])), 2),
                                         "dist_median": round(float(np.median(np.linalg.norm(shift, axis=1))), 2)}}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--gt", type=Path, required=True)
    p.add_argument("--calibration", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--v-offset", type=float, default=0.0, help="GSR piksel v'sine eklenecek kaydırma (panorama uzayına)")
    args = p.parse_args()
    rows = np.load(args.gt)
    out, summary = correct_positions(rows, PitchCalibration.load(args.calibration), v_offset=args.v_offset)
    np.save(args.out, out)
    summary.update({"gt": str(args.gt), "calibration": str(args.calibration), "v_offset": args.v_offset, "out": str(args.out)})
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
