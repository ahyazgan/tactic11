"""Canlı telestrasyon işçisi: canlı modun segment çıktısını izler, çizimli video üretir (venv-cv).

`scripts.track_live` her segmenti `<watch>/seg_XXXX.mp4` ve takip karelerini
`<watch>/frames/seg_XXXX.json` olarak bırakır. Bu işçi yeni gelen her segment için:

- `<watch>/tele/seg_XXXX.mp4` — halka, blok çizgileri, faz etiketi (tarayıcıda
  oynatılabilen H.264; PyAV yoksa mp4v)
- `<watch>/tele/seg_XXXX.marks.json` — kare başına çizim öğeleri (panel katmanı)
- `<watch>/tele/latest.json` — panelin okuyacağı son segment özeti

Telestratör durumu (hücum yönü, sahiplik, hat yumuşatma, etiket) segmentler
arasında korunur. `--swap-at-minute 45`: segment başlangıç dakikası bu değere
ulaşınca ev sahibinin hücum yönü kendiliğinden ters çevrilir (ikinci yarı). Bir segment hata verirse `seg_XXXX.error.json` yazılır ve
sonrakine geçilir; yarım yazılmış takip JSON'u hata sayılmaz, sonraki turda
yeniden denenir. Dondurulmuş takip koduna dokunmaz; `canli_mac --telestration`
bu işçiyi takiple birlikte başlatır.

    venv-cv\\Scripts\\python.exe -m scripts.telestrate_live --watch data/tracking/live/990201 \\
        --calibration saha.json --home-attack x+
"""
from __future__ import annotations

import argparse
import json
import time
import traceback
from datetime import UTC, datetime
from pathlib import Path

from app.tracking.calibration import PitchCalibration
from app.tracking.telestration import Telestrator
from scripts.telestrate_video import HOME_ATTACK, render_segment, warn_calibration


def pending(watch: Path, out: Path) -> list[tuple[Path, Path, str]]:
    """İşlenmemiş segmentler: takip JSON'u ve videosu var, çıktı ya da hata kaydı yok."""
    items = []
    for frames_json in sorted((watch / "frames").glob("seg_*.json")):
        stem = frames_json.stem
        video = watch / f"{stem}.mp4"
        if video.exists() and not (out / f"{stem}.mp4").exists() and not (out / f"{stem}.error.json").exists():
            items.append((video, frames_json, stem))
    return items


def write_json(path: Path, payload: dict) -> None:
    """Okuyucu yarım dosya görmesin: geçici dosyaya yaz, sonra yerine koy."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def segment_attack(payload: dict, home_attack: int, swap_at_minute: float | None) -> int:
    """Segmentin ev sahibi hücum yönü: başlangıç dakikası `swap_at_minute`'e ulaştıysa ters."""
    minutes = [float(f["minute"]) for f in payload.get("frames", []) if "minute" in f]
    if swap_at_minute is None or not minutes or min(minutes) < swap_at_minute:
        return home_attack
    return -home_attack


def process(video: Path, frames_json: Path, stem: str, out: Path, calib: PitchCalibration,
            tele: Telestrator | None, *, home_attack: int, width: int, h264: bool,
            swap_at_minute: float | None = None) -> Telestrator | None:
    try:
        payload = json.loads(frames_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return tele  # takip hâlâ yazıyor olabilir; sonraki turda yeniden dene
    home_attack = segment_attack(payload, home_attack, swap_at_minute)
    if tele is not None:
        tele.set_home_attack(home_attack)
    partial = out / f"{stem}.tmp.mp4"  # uzantı .mp4 kalmalı: yazıcılar biçimi uzantıdan seçer
    try:
        summary, log, tele = render_segment(video, payload, calib, partial, home_attack=home_attack, tele=tele,
                                            width=width, keep_marks=True, h264=h264)
    except Exception as exc:  # noqa: BLE001 — canlıda tek segment hatası akışı durdurmaz
        partial.unlink(missing_ok=True)
        write_json(out / f"{stem}.error.json", {"segment": stem, "error": repr(exc),
                                                "traceback": traceback.format_exc()})
        print(f"[telestrasyon] {stem}: hata, atlandı ({exc})", flush=True)
        return tele
    partial.replace(out / f"{stem}.mp4")
    write_json(out / f"{stem}.marks.json", {"summary": summary, "frames": log})
    write_json(out / "latest.json", {"segment": stem, "video": f"{stem}.mp4", "marks": f"{stem}.marks.json",
                                     "summary": summary, "updated": datetime.now(UTC).isoformat()})
    print(f"[telestrasyon] {stem}: {summary['frames_written']} kare · çizilen %{100 * summary['drawn_ratio']:.0f}"
          f" · etiket {summary['label'] or '-'}", flush=True)
    return tele


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--watch", type=Path, required=True)
    p.add_argument("--calibration", type=Path, required=True)
    p.add_argument("--home-attack", default="auto", choices=sorted(HOME_ATTACK))
    p.add_argument("--swap-at-minute", type=float, default=None,
                   help="Bu dakikadan başlayan segmentlerde ev sahibi hücum yönünü ters çevir (ör. 45)")
    p.add_argument("--width", type=int, default=1280)
    p.add_argument("--poll-seconds", type=float, default=3.0)
    p.add_argument("--once", action="store_true", help="Mevcut segmentleri işle ve çık")
    p.add_argument("--no-h264", action="store_true", help="mp4v ile yaz (tarayıcıda oynamayabilir)")
    args = p.parse_args()

    calib = PitchCalibration.load(args.calibration)
    warn_calibration(calib)
    out = args.watch / "tele"
    out.mkdir(parents=True, exist_ok=True)
    tele: Telestrator | None = None
    while True:
        for video, frames_json, stem in pending(args.watch, out):
            tele = process(video, frames_json, stem, out, calib, tele, home_attack=HOME_ATTACK[args.home_attack],
                           width=args.width, h264=not args.no_h264, swap_at_minute=args.swap_at_minute)
        if args.once:
            return 0
        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
