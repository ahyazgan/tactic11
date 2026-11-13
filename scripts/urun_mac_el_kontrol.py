"""Ürün maç sınavının el kontrolü için kare sayfaları üretir (venv-cv; opencv gerekir).

Ön kayıt: docs/measurements/product-full-match-exam-preregistration.json, `hand_review`.
Yöntem iki adımlıdır ve sıra önemlidir: önce `NN_ham.jpg` (tahminsiz) açılıp sahadaki
oyuncular sayılır, SONRA `NN_tahmin.jpg` açılıp her işaret kişi ya da hayalet diye işaretlenir.

Sınır: ürün çıktısı kutu değil saha konumu taşır. İşaretler, kalibrasyonun görüntü→saha
dönüşümü ızgara üzerinde tersine çevrilerek görüntüye geri düşürülür; hata ızgara adımı
(varsayılan 12 px) kadardır, kalibrasyonun kendi hatası buna eklenir. İşaret oyuncunun
ayak noktasını gösterir, gövdesini değil.

Kullanım:
    venv-cv\\Scripts\\python.exe -m scripts.urun_mac_el_kontrol --result sonuc.json \\
        --frames job_x_frames.json --video mac.mp4 --calibration calib.json --out-dir klasor
"""
from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from app.tracking.calibration import PitchCalibration

GRID_STEP_PX = 12
HOME_BGR, AWAY_BGR, OTHER_BGR, BALL_BGR = (40, 40, 230), (230, 140, 30), (200, 200, 200), (0, 230, 255)


def nearest_frame(frames: Sequence[dict[str, Any]], minute: float) -> dict[str, Any]:
    """Verilen maç dakikasına en yakın çıktı karesi."""
    candidates = [f for f in frames if f.get("minute") is not None]
    if not candidates:
        raise ValueError("çıktıda dakikası olan kare yok")
    return min(candidates, key=lambda f: abs(float(f["minute"]) - minute))


def inverse_lookup(calibration: PitchCalibration,
                   step: int = GRID_STEP_PX) -> Callable[[float, float], tuple[int, int] | None]:
    """Saha (0-100 normalize) → görüntü pikseli; görüntü dışına düşen konum için None.

    Kalibrasyonun yalnız görüntü→saha yönü vardır (TPS artık düzeltmesinin kapalı tersi yok);
    o yüzden görüntü ızgarası ileri yönde bir kez hesaplanır, en yakın ızgara noktası aranır.
    """
    width, height = calibration.image_size
    us, vs = np.meshgrid(np.arange(0, width, step), np.arange(0, height, step))
    pixels = np.stack([us.ravel(), vs.ravel()], axis=1)
    pitch = np.array([calibration.image_to_normalized(float(u), float(v), clamp=False) for u, v in pixels])
    # Izgara adımının saha karşılığından uzak düşen konum görüntüde yoktur.
    tolerance = 3.0

    def lookup(x: float, y: float) -> tuple[int, int] | None:
        distance = np.hypot(pitch[:, 0] - x, pitch[:, 1] - y)
        best = int(distance.argmin())
        if distance[best] > tolerance:
            return None
        return int(pixels[best, 0]), int(pixels[best, 1])

    return lookup


def sheet_rows(result: dict[str, Any], frames: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """El kontrol satırları: ön kayıtlı örnek dakikalar, tahmin sayısı ve doldurulacak boş alanlar."""
    rows = []
    for index, minute in enumerate(result.get("review_minutes") or [], start=1):
        frame = nearest_frame(frames, float(minute))
        rows.append({
            "n": index, "minute": float(frame["minute"]), "predicted_players": len(frame.get("players") or []),
            "hand_count": None, "predictions_on_a_person": None, "ghosts": None,
        })
    return rows


def review_verdict(rows: Sequence[dict[str, Any]], min_recall: float, max_ghost_share: float) -> dict[str, Any]:
    """Doldurulmuş satırlardan ön kayıtlı iki şart; eksik satır varsa hüküm verilmez."""
    if not rows or any(r.get(k) is None for r in rows for k in ("hand_count", "predictions_on_a_person", "ghosts")):
        return {"complete": False}
    people = sum(r["hand_count"] for r in rows)
    matched = sum(r["predictions_on_a_person"] for r in rows)
    ghosts = sum(r["ghosts"] for r in rows)
    recall = matched / people if people else 0.0
    ghost_share = ghosts / (matched + ghosts) if matched + ghosts else 0.0
    return {"complete": True, "recall": round(recall, 4), "ghost_share": round(ghost_share, 4),
            "passed": recall >= min_recall and ghost_share <= max_ghost_share}


def _team_color(player: dict[str, Any], home: Any, away: Any) -> tuple[int, int, int]:
    team = player.get("team_external_id")
    return HOME_BGR if team == home else AWAY_BGR if team == away else OTHER_BGR


def render(video: str, frames_payload: dict[str, Any], rows: list[dict[str, Any]],
           calibration: PitchCalibration, out_dir: Path) -> None:
    import cv2

    out_dir.mkdir(parents=True, exist_ok=True)
    lookup = inverse_lookup(calibration)
    home, away = frames_payload.get("home_team_external_id"), frames_payload.get("away_team_external_id")
    cap = cv2.VideoCapture(video)
    try:
        for row in rows:
            frame = nearest_frame(frames_payload["frames"], row["minute"])
            cap.set(cv2.CAP_PROP_POS_MSEC, float(frame["minute"]) * 60_000.0)
            ok, image = cap.read()
            if not ok:
                raise RuntimeError(f"video karesi okunamadı: {frame['minute']:.2f}. dakika")
            cv2.imwrite(str(out_dir / f"{row['n']:02d}_ham.jpg"), image, [cv2.IMWRITE_JPEG_QUALITY, 90])
            off_image = 0
            for player in frame.get("players") or []:
                at = lookup(float(player["x"]), float(player["y"]))
                if at is None:
                    off_image += 1
                    continue
                cv2.circle(image, at, 16, _team_color(player, home, away), 3)
            ball = frame.get("ball")
            ball_at = lookup(float(ball["x"]), float(ball["y"])) if ball else None
            if ball_at:
                cv2.circle(image, ball_at, 8, BALL_BGR, 2)
            row["predictions_off_image"] = off_image
            cv2.imwrite(str(out_dir / f"{row['n']:02d}_tahmin.jpg"), image, [cv2.IMWRITE_JPEG_QUALITY, 90])
    finally:
        cap.release()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--result", required=True, help="sınav sonucu JSON'u (review_minutes içerir)")
    p.add_argument("--frames", required=True, help="işin çıktı kareleri JSON'u")
    p.add_argument("--video", required=True)
    p.add_argument("--calibration", required=True)
    p.add_argument("--out-dir", required=True)
    args = p.parse_args()
    with open(args.result, encoding="utf-8") as f:
        result = json.load(f)
    with open(args.frames, encoding="utf-8") as f:
        payload = json.load(f)
    rows = sheet_rows(result, payload["frames"])
    if not rows:
        print("sonuçta örnek dakika yok; iş kare üretmemiş olabilir")
        return 1
    out_dir = Path(args.out_dir)
    render(args.video, payload, rows, PitchCalibration.load(args.calibration), out_dir)
    with open(out_dir / "el-kontrol.json", "w", encoding="utf-8") as f:
        json.dump({"method": "önce NN_ham.jpg'de oyuncuları say, sonra NN_tahmin.jpg'de işaretleri kişi/hayalet ayır",
                   "rows": rows}, f, ensure_ascii=False, indent=2)
    print(f"{len(rows)} kare yazıldı: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
