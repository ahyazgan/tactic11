"""Ürün çıktısındaki takım etiketini karedeki forma rengiyle karşılaştırır (venv-cv; opencv gerekir).

Yalnız iki forması HSV'de açıkça ayrılan maç içindir (117093: doygun mavi ve beyaz).
Her oyuncu işareti görüntüye geri düşürülür, çevresindeki bölgede mavi ve beyaz piksel
sayılır; biri belirgin baskınsa o forma kabul edilir, değilse işaret "belirsiz" kalır ve
ölçüme girmez. Takım numarası ↔ forma eşlemesi veriden seçilir (iki eşlemeden yükseği).

Sınırlar: referans insan etiketi değil, basit bir renk kuralıdır; işaret ayağı tam
göstermediği için bölge geniş tutulur ve yan yana oyuncularda belirsiz kalır. Kaleci ve
hakem formaları belirsizdir. Sonuç yalnız etiketlenebilen işaretlerin uyumudur.

Kullanım:
    venv-cv\\Scripts\\python.exe -m scripts.soccertrack_v2.team_color_spot_check \
        --frames job_x_frames.json --video mac.mp4 --calibration calib.json --samples 120 --out sonuc.json
"""
from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

from app.tracking.calibration import PitchCalibration
from scripts.urun_mac_el_kontrol import frame_command, inverse_lookup

FAR_Y, FAR_HEIGHT_PX, HEIGHT_PER_Y = 150.0, 35.0, 95.0 / 550.0
MIN_TORSO_SHARE, DOMINANCE = 0.5, 1.5


def player_height_px(image_y: float) -> float:
    """117093 panoramasında oyuncu boyu (piksel): uzak kenarda ~35, yakın kenarda ~130."""
    return FAR_HEIGHT_PX + max(0.0, image_y - FAR_Y) * HEIGHT_PER_Y


def kit_label(hsv: np.ndarray, height_px: float) -> str | None:
    """HSV piksellerinden forma: "blue", "white" ya da belirsizse None."""
    h, s, v = (hsv[:, i].astype(int) for i in range(3))
    blue = int(((h > 95) & (h < 130) & (s > 110) & (v > 70)).sum())
    white = int(((s < 70) & (v > 165)).sum())
    torso = 0.26 * height_px * 0.35 * height_px
    if blue > MIN_TORSO_SHARE * torso and blue > DOMINANCE * white:
        return "blue"
    if white > MIN_TORSO_SHARE * torso and white > DOMINANCE * blue:
        return "white"
    return None


def agreement(pairs: Counter[tuple[str, str]]) -> dict[str, Any]:
    """(takım, forma) sayımlarından uyum; takım↔forma eşlemesi iki seçenekten yükseği."""
    straight = pairs[("home", "blue")] + pairs[("away", "white")]
    crossed = pairs[("home", "white")] + pairs[("away", "blue")]
    total = straight + crossed
    return {"labelled": total, "agree": max(straight, crossed),
            "agreement": round(max(straight, crossed) / total, 4) if total else None,
            "home_kit": "blue" if straight >= crossed else "white"}


def main() -> int:
    import cv2

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--frames", required=True)
    p.add_argument("--video", required=True)
    p.add_argument("--calibration", required=True)
    p.add_argument("--samples", type=int, default=120)
    p.add_argument("--chunk-minutes", type=float, default=5.0)
    p.add_argument("--out", required=True)
    args = p.parse_args()
    from scripts.canli_mac import find_ffmpeg

    payload = json.loads(Path(args.frames).read_text(encoding="utf-8"))
    frames = [f for f in payload["frames"] if f.get("players")]
    picked = [frames[i] for i in np.linspace(0, len(frames) - 1, args.samples).round().astype(int)]
    lookup = inverse_lookup(PitchCalibration.load(args.calibration))
    home, away = payload.get("home_team_external_id"), payload.get("away_team_external_id")
    ffmpeg, total, by_chunk, counts = find_ffmpeg(), Counter(), {}, Counter()
    with tempfile.TemporaryDirectory() as tmp:
        for frame in picked:
            raw = Path(tmp) / "kare.jpg"
            subprocess.run(frame_command(ffmpeg, args.video, float(frame["minute"]) * 60.0, raw), check=True)  # noqa: S603
            hsv_image = cv2.cvtColor(cv2.imread(str(raw)), cv2.COLOR_BGR2HSV)
            chunk = by_chunk.setdefault(int(float(frame["minute"]) // args.chunk_minutes), Counter())
            for player in frame["players"]:
                team = {home: "home", away: "away"}.get(player.get("team_external_id"))
                at = lookup(float(player["x"]), float(player["y"]))
                if at is None or team is None:
                    counts["off_image" if at is None else "no_team"] += 1
                    continue
                height = player_height_px(at[1])
                region = hsv_image[max(0, int(at[1] - height)):max(0, int(at[1] - 0.2 * height)),
                                   max(0, int(at[0] - 0.45 * height)):int(at[0] + 0.45 * height)]
                kit = kit_label(region.reshape(-1, 3), height) if region.size else None
                if kit is None:
                    counts["unclear_kit"] += 1
                    continue
                total[(team, kit)] += 1
                chunk[(team, kit)] += 1
    result = {"frames_sampled": len(picked), "overall": agreement(total), "skipped": dict(counts),
              "pairs": {f"{t}/{k}": n for (t, k), n in sorted(total.items())},
              "by_chunk": {str(i): agreement(c) for i, c in sorted(by_chunk.items())}}
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["overall"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
