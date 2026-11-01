"""Canlı telestrasyon işçisi: canlı modun segment çıktısını izler, çizimli video üretir (venv-cv).

`scripts.track_live` her segmenti `<watch>/seg_XXXX.mp4` ve takip karelerini
`<watch>/frames/seg_XXXX.json` olarak bırakır. Bu işçi yeni gelen her segment için:

- `<watch>/tele/seg_XXXX.mp4` — halka, blok çizgileri, faz etiketi (tarayıcıda
  oynatılabilen H.264; PyAV yoksa mp4v)
- `<watch>/tele/seg_XXXX.marks.json` — kare başına çizim öğeleri (panel katmanı)
- `<watch>/tele/latest.json` — panelin okuyacağı son segment özeti

Telestratör durumu (hücum yönü, sahiplik, hat yumuşatma, etiket) ardışık segmentler
arasında korunur; yeni segment öncekinin bittiği yerden başlamıyorsa (`canli_mac
--keep-up` aradakileri atladı, > `CONTINUITY_GAP_S`) durum sıfırlanır, çünkü bir
buçuk dakika önceki hat ve sahiplik yeni resme karışmamalı. `--swap-at-minute 45`: segment başlangıç dakikası bu değere
ulaşınca ev sahibinin hücum yönü kendiliğinden ters çevrilir (ikinci yarı). Bir segment hata verirse `seg_XXXX.error.json` yazılır ve
sonrakine geçilir; yarım yazılmış takip JSON'u hata sayılmaz, sonraki turda
yeniden denenir. Dondurulmuş takip koduna dokunmaz; `canli_mac --telestration`
bu işçiyi takiple birlikte başlatır.

Takım: `<watch>/kit_colors/seg_XXXX.json` varsa takım ataması forma renk oranıyla
yeniden kurulur (`app.tracking.team_refit`; güneşte beyaza dönen uzak oyuncular için,
çapa `<watch>/team_refit_anchor.json`). Top: `<watch>/ball_candidates/seg_XXXX.json`
varsa (`scripts.track_live_candidates`)
karelerin topu çizimden önce aday iziyle değiştirilir (`app.tracking.ball_track`);
sahiplik, dolayısıyla savunan takım ve pres bu topa göre hesaplanır. `--match-id` ve
`--tenant` verilirse düzeltilmiş kareler `<watch>/frames_ball/` altına yazılır ve
veritabanındaki aynı kareler güncellenir (aktarım zaman damgasıyla günceller). Takip
işçisinin kendi aktarımı bunun üstüne yazmasın diye segment, işçinin durum dosyasında
"işlendi" görünmeden aktarılmaz; aktarılan segment `.ingested` işaretiyle bir kez gider.

    venv-cv\\Scripts\\python.exe -m scripts.telestrate_live --watch data/tracking/live/990201 \\
        --calibration saha.json --home-attack x+
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
import traceback
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.tracking.ball_track import refine_segment
from app.tracking.calibration import PitchCalibration
from app.tracking.team_refit import refit_segment
from app.tracking.telestration import Telestrator
from scripts.telestrate_video import HOME_ATTACK, render_segment, warn_calibration
from scripts.track_live import PROJECT_ROOT, STATE_FILE, default_ingest_python


@dataclass(frozen=True)
class IngestTarget:
    """Düzeltilmiş karelerin yazılacağı maç (takip işçisinin aktarımıyla aynı)."""
    tenant: str
    match_id: int
    database_url: str | None = None
    python: str = ""


def tracked_segments(watch: Path) -> set[str]:
    """Takip işçisinin aktarımını bitirdiği segmentler (durum dosyası; uzantısız)."""
    try:
        state = json.loads((watch / STATE_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    return {Path(name).stem for name in state.get("processed", [])}


def ingest_refined(watch: Path, target: IngestTarget) -> int:
    """Takibi aktarılmış ama düzeltilmiş hali aktarılmamış segmentleri veritabanına yaz."""
    done = tracked_segments(watch)
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    if target.database_url:
        env["DATABASE_URL"] = target.database_url
    written = 0
    for path in sorted((watch / "frames_ball").glob("seg_*.json")):
        marker = path.with_suffix(".ingested")
        if marker.exists() or path.stem not in done:
            continue
        run = subprocess.run(  # noqa: S603 — sabit komut listesi
            [target.python or default_ingest_python(), "-m", "scripts.ingest_tracking_json", "--json", str(path),
             "--tenant", target.tenant, "--match-id", str(target.match_id), "--append"],
            capture_output=True, text=True, cwd=str(PROJECT_ROOT), check=False, env=env)
        if run.returncode != 0:
            print(f"[telestrasyon] {path.stem}: düzeltilmiş top aktarılamadı, yeniden denenecek — "
                  f"{(run.stderr or run.stdout).strip()[-200:]}", flush=True)
            continue
        marker.touch()
        written += 1
    return written


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


CONTINUITY_GAP_S = 2.0  # önceki segmentin son karesiyle bu segmentin ilk karesi arası en çok


@dataclass
class LiveState:
    """Segmentler arası taşınan durum: telestratör ve işlenen son karenin maç dakikası."""
    tele: Telestrator | None = None
    end_minute: float | None = None


def continues(previous_end: float | None, payload: dict) -> bool:
    """Segment öncekinin bittiği yerden mi başlıyor (aradaki boşluk ≤ CONTINUITY_GAP_S)?"""
    minutes = [float(f["minute"]) for f in payload.get("frames", []) if "minute" in f]
    if previous_end is None or not minutes:
        return True
    return (min(minutes) - previous_end) * 60.0 <= CONTINUITY_GAP_S


def process(video: Path, frames_json: Path, stem: str, out: Path, calib: PitchCalibration,
            state: LiveState, *, home_attack: int, width: int, h264: bool,
            swap_at_minute: float | None = None, keep_refined: bool = False) -> None:
    try:
        payload = json.loads(frames_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return  # takip hâlâ yazıyor olabilir; sonraki turda yeniden dene
    watch = frames_json.parent.parent
    kit_colors = watch / "kit_colors" / frames_json.name
    if kit_colors.exists():
        team = refit_segment(payload.get("frames", []), json.loads(kit_colors.read_text(encoding="utf-8")),
                             watch / "team_refit_anchor.json",
                             int(payload["home_team_external_id"]), int(payload["away_team_external_id"]))
        note = team["reason"] or f"{team['changed']} oyuncu gözlemi değişti · atanmayan takip {team['unassigned']}"
        print(f"[telestrasyon] {stem}: takım yeniden atama — {note}", flush=True)
    candidates = frames_json.parent.parent / "ball_candidates" / frames_json.name
    if candidates.exists():
        ball = refine_segment(payload.get("frames", []), json.loads(candidates.read_text(encoding="utf-8")), calib)
        print(f"[telestrasyon] {stem}: top izi {ball['tracked']} örnek · sabit {ball['static_removed']}",
              flush=True)
        if keep_refined:
            refined = frames_json.parent.parent / "frames_ball"
            refined.mkdir(exist_ok=True)
            write_json(refined / frames_json.name, payload)
    if state.tele is not None and not continues(state.end_minute, payload):
        print(f"[telestrasyon] {stem}: önceki segmentle süreklilik yok — durum sıfırlandı", flush=True)
        state.tele = None
    minutes = [float(f["minute"]) for f in payload.get("frames", []) if "minute" in f]
    if minutes:
        state.end_minute = max(minutes)
    home_attack = segment_attack(payload, home_attack, swap_at_minute)
    tele = state.tele
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
        state.tele = tele
        return
    state.tele = tele
    partial.replace(out / f"{stem}.mp4")
    write_json(out / f"{stem}.marks.json", {"summary": summary, "frames": log})
    write_json(out / "latest.json", {"segment": stem, "video": f"{stem}.mp4", "marks": f"{stem}.marks.json",
                                     "summary": summary, "updated": datetime.now(UTC).isoformat()})
    print(f"[telestrasyon] {stem}: {summary['frames_written']} kare · çizilen %{100 * summary['drawn_ratio']:.0f}"
          f" · etiket {summary['label'] or '-'}", flush=True)


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
    p.add_argument("--match-id", type=int, default=None, help="düzeltilmiş topu bu maçın karelerine yaz")
    p.add_argument("--tenant", default=None)
    p.add_argument("--database-url", default=None)
    p.add_argument("--ingest-python", default=None)
    args = p.parse_args()
    if (args.match_id is None) != (args.tenant is None):
        p.error("--match-id ve --tenant birlikte verilir")
    target = None if args.match_id is None else IngestTarget(
        args.tenant, args.match_id, args.database_url, args.ingest_python or default_ingest_python())

    calib = PitchCalibration.load(args.calibration)
    warn_calibration(calib)
    out = args.watch / "tele"
    out.mkdir(parents=True, exist_ok=True)
    state = LiveState()
    while True:
        for video, frames_json, stem in pending(args.watch, out):
            process(video, frames_json, stem, out, calib, state, home_attack=HOME_ATTACK[args.home_attack],
                    width=args.width, h264=not args.no_h264, swap_at_minute=args.swap_at_minute,
                    keep_refined=target is not None)
        if target is not None:
            ingest_refined(args.watch, target)
        if args.once:
            return 0
        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
