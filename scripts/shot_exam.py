"""Profesyonel gündüz sınav seti: örnekleme, etiket sayfaları, çekim ayırıcı ölçümü (venv-cv).

Ön kayıt ve kurallar: docs/measurements/shot-exam-plan.json. Görüntüler repoda değildir.

    venv-cv\\Scripts\\python.exe -X utf8 -m scripts.shot_exam inspect --group control
    venv-cv\\Scripts\\python.exe -X utf8 -m scripts.shot_exam sheets --group development --out <klasör>
    venv-cv\\Scripts\\python.exe -X utf8 -m scripts.shot_exam eval --group development \\
        --labels docs/measurements/shot-exam-labels-development.json

`inspect` yalnız sayı üretir, görüntü yazmaz: kontrol kesitleri görülmeden doğrulanır.
Etiket dosyası biçimi: {"<maç>": {"other": [kare no, ...]}}; listede olmayan kare "main".
"""
from __future__ import annotations

import argparse
import json
from collections.abc import Iterator
from pathlib import Path

import cv2
import numpy as np

PLAN = Path("docs/measurements/shot-exam-plan.json")
STEP_S = 3.0
MAX_FRAMES = 120
SHEET_COLS, SHEET_ROWS = 5, 4
TILE_W, TILE_H = 384, 216


def group_matches(group: str) -> dict[str, Path]:
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    return {name: Path(item["file"]) for name, item in plan["matches"][group].items()}


def sampled_frames(video: Path) -> Iterator[tuple[int, np.ndarray]]:
    """(örnek no, BGR kare). Örnek no zaman sırasıdır: t = no × STEP_S."""
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise SystemExit(f"video açılamadı: {video}")
    try:
        for i in range(MAX_FRAMES):
            cap.set(cv2.CAP_PROP_POS_MSEC, i * STEP_S * 1000.0)
            ok, frame = cap.read()
            if not ok:
                return
            yield i, frame
    finally:
        cap.release()


def inspect(group: str) -> int:
    for name, video in group_matches(group).items():
        grays = [float(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).mean()) for _, f in sampled_frames(video)]
        cap = cv2.VideoCapture(str(video))
        size = (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
        seconds = cap.get(cv2.CAP_PROP_FRAME_COUNT) / (cap.get(cv2.CAP_PROP_FPS) or 1.0)
        cap.release()
        print(f"{name}: {size[0]}x{size[1]} · {seconds:.0f} sn · {len(grays)} örnek · "
              f"parlaklık medyan {np.median(grays):.0f} (en düşük {min(grays):.0f}, en yüksek {max(grays):.0f})")
    return 0


def write_sheet(path: Path, tiles: list[np.ndarray]) -> None:
    """Kareleri numaralı ızgara sayfası olarak yaz; eksik hücreler siyah kalır."""
    filled = tiles + [np.zeros((TILE_H, TILE_W, 3), np.uint8)] * (SHEET_COLS * SHEET_ROWS - len(tiles))
    rows = [np.hstack(filled[r * SHEET_COLS:(r + 1) * SHEET_COLS]) for r in range(SHEET_ROWS)]
    cv2.imwrite(str(path), np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 82])


def sheets(group: str, out: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    per_sheet = SHEET_COLS * SHEET_ROWS
    for name, video in group_matches(group).items():
        tiles: list[np.ndarray] = []
        page = 0
        for i, frame in sampled_frames(video):
            tile = cv2.resize(frame, (TILE_W, TILE_H), interpolation=cv2.INTER_AREA)
            cv2.rectangle(tile, (0, 0), (70, 34), (0, 0, 0), -1)
            cv2.putText(tile, str(i), (6, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.85, (0, 255, 255), 2)
            tiles.append(tile)
            if len(tiles) == per_sheet:
                write_sheet(out / f"{name}_{page:02d}.jpg", tiles)
                page += 1
                tiles = []
        if tiles:
            write_sheet(out / f"{name}_{page:02d}.jpg", tiles)
            page += 1
        print(f"{name}: {page} sayfa")
    return 0


def wilson(hits: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson aralığı; toplam 0 ise (0, 1)."""
    if total == 0:
        return 0.0, 1.0
    p = hits / total
    denom = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denom
    margin = z * np.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denom
    return float(max(0.0, centre - margin)), float(min(1.0, centre + margin))


def evaluate(group: str, labels_path: Path, misses: bool) -> int:
    from app.tracking.shot_filter import classify_shot  # noqa: PLC0415

    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    total = {"main": [0, 0], "other": [0, 0]}
    for name, video in group_matches(group).items():
        others = set(labels[name]["other"])
        per = {"main": [0, 0], "other": [0, 0]}
        wrong: list[tuple[int, str]] = []
        for i, frame in sampled_frames(video):
            truth = "other" if i in others else "main"
            verdict = classify_shot(frame)
            per[truth][0] += int(verdict.is_main)
            per[truth][1] += 1
            if verdict.is_main != (truth == "main"):
                wrong.append((i, verdict.reason))
        for key in total:
            total[key][0] += per[key][0]
            total[key][1] += per[key][1]
        print(f"{name}: main geçen {per['main'][0]}/{per['main'][1]} · other sızan {per['other'][0]}/{per['other'][1]}")
        if misses:
            print("  hatalı:", wrong)
    for key, title in (("main", "main geçme"), ("other", "other sızıntı")):
        hits, n = total[key]
        low, high = wilson(hits, n)
        print(f"TOPLAM {title}: {hits}/{n} = %{100 * hits / max(n, 1):.1f} (Wilson %{100 * low:.1f}–%{100 * high:.1f})")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("inspect")
    i.add_argument("--group", required=True, choices=["development", "control"])
    s = sub.add_parser("sheets")
    s.add_argument("--group", required=True, choices=["development", "control"])
    s.add_argument("--out", required=True)
    e = sub.add_parser("eval")
    e.add_argument("--group", required=True, choices=["development", "control"])
    e.add_argument("--labels", required=True)
    e.add_argument("--show-misses", action="store_true", help="yalnız geliştirme grubunda kullanılır")
    a = p.parse_args()
    if a.cmd == "inspect":
        return inspect(a.group)
    if a.cmd == "sheets":
        return sheets(a.group, Path(a.out))
    if a.show_misses and a.group == "control":
        p.error("kontrolde hata dökümü yok: ön kayda göre eşik ayarına kapalı")
    return evaluate(a.group, Path(a.labels), a.show_misses)


if __name__ == "__main__":
    raise SystemExit(main())
