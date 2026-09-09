"""Canlı maç: yeni video segmentlerini geldikçe işle → aynı maça ekle (venv-cv).

Kamera/encoder maç boyunca klasöre segment yazar (HLS/ffmpeg segment muxer ya da
kulüp yazılımı). Bu script klasörü izler; her yeni segmenti takip hattından
geçirip kareleri **ekleyerek** DB'ye yazar. Canlı karar paneli
(`/admin/matches/{id}/live-decision`) o kareleri okuyup şekil/pres sinyali üretir.

Segment → maç dakikası eşlemesi: segmentler ada göre sıralanır, i. segmentin
başlangıcı `--start-minute + i * --segment-seconds/60`. Kamera maç başında
başlamadıysa `--start-minute` ile kaydır. (Daha sağlamı: dosya adında dakika
taşımak — `--minute-from-name` deseniyle.)

Örnek ffmpeg ile segment üretimi (kulüp tarafında):
    ffmpeg -i rtsp://kamera -c copy -f segment -segment_time 30 \\
           -reset_timestamps 1 data/tracking/live/seg_%04d.mp4

Kullanım (venv-cv):
    venv-cv\\Scripts\\python.exe -m scripts.track_live \\
        --watch data/tracking/live --calibration data/tracking/calibrations/saha.json \\
        --match-id 990100 --home-team 611 --away-team 612 --tenant t-default \\
        --segment-seconds 30 --weights data/tracking/models/rfdetr_mixed_small

Ctrl+C ile durur. İşlenen segmentler `<watch>/.processed` altına taşınmaz —
adları bir durum dosyasında tutulur, böylece yeniden başlatınca kaldığı yerden devam eder.

**Sıcak model (varsayılan):** model bir kez yüklenip fp16 derlenir, sonraki
segmentler aynı dedektörle işlenir. Her segment için ayrı süreç açmak (eski
davranış) segment başına ~30-40 sn model yükleme/derleme maliyeti getiriyordu;
canlı maçta bu tek başına gerçek zamana yetişmeyi imkânsız kılıyor. Yalıtım
gerekirse `--isolate` ile eski davranışa dönülür (segment çökmesi izleyiciyi
etkilemez, karşılığında her segment yeniden ısınır).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

VIDEO_EXT = {".mp4", ".mkv", ".ts", ".mov"}
STATE_FILE = ".track_live_state.json"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAX_INGEST_RETRY = 3


def default_ingest_python() -> str:
    """Ingest ana ortamda koşar (venv-cv'de sqlalchemy yok — CV ve DB ayrı)."""
    sub = "Scripts/python.exe" if sys.platform == "win32" else "bin/python"
    cand = PROJECT_ROOT / "venv" / sub
    return str(cand) if cand.exists() else sys.executable


class WarmTracker:
    """Modeli açık tutan takip işçisi — segmentler arasında yeniden yüklenmez.

    Dedektör ilk `detect()` çağrısında kare boyutuna göre batch'ini sabitleyip
    fp16 derliyor (bkz. app/tracking/detect.py `_prepare`). Bu yüzden sıcak
    dedektör YALNIZ aynı çözünürlükteki segmentlerde geçerli; kaynak çözünürlük
    değişirse (kamera/encoder profili değişti) dedektör yeniden kurulur, yoksa
    derlenmiş sabit batch ile dilim sayısı uyuşmaz.
    """

    def __init__(self, *, calibration: str, detector_cfg, pipeline_kwargs: dict):
        from app.tracking.calibration import PitchCalibration

        self.calib = PitchCalibration.load(calibration)
        self._detector_cfg = detector_cfg
        self._pipeline_kwargs = pipeline_kwargs
        self._detector = None
        self._size: tuple[int, int] | None = None
        self.warmup_seconds = 0.0
        # İlk segmentte bulunan forma renkleri; sonraki segmentlere çapa olarak
        # geçilir ki ev/deplasman etiketleri yer değiştirmesin.
        self.team_anchor = None

    def _ensure_detector(self, width: int, height: int):
        from app.tracking.detect import RFDetrDetector

        if self._detector is not None and self._size != (width, height):
            print(f"  ! çözünürlük {self._size} → {(width, height)} değişti, "
                  f"model yeniden kuruluyor", flush=True)
            self._detector = None
        if self._detector is None:
            t0 = time.time()
            self._detector = RFDetrDetector(self._detector_cfg)
            self._size = (width, height)
            self.warmup_seconds = time.time() - t0
        return self._detector

    def run(self, video: Path, *, out_json: Path, offset_minutes: float,
            match_id: int, home_team: int, away_team: int, period: int) -> dict:
        """Tek segmenti sıcak modelle işle → frames JSON yaz, özet döndür."""
        from app.tracking.frames import frames_to_json
        from app.tracking.pipeline import PipelineConfig, process_video, video_info

        info = video_info(str(video))
        det = self._ensure_detector(int(info["width"]), int(info["height"]))
        cfg = PipelineConfig(
            detector=self._detector_cfg,
            clip_offset_minutes=offset_minutes, period=period,
            **self._pipeline_kwargs,
        )
        frames, summary = process_video(
            str(video), self.calib, match_id=match_id,
            home_team_id=home_team, away_team_id=away_team, cfg=cfg, detector=det,
            team_anchor=self.team_anchor,
        )
        # İlk geçerli atamayı çapa olarak sabitle (sonraki segmentler buna uyar).
        if self.team_anchor is None:
            colors = summary.get("team_colors") or []
            if len(colors) == 2 and any(any(c) for c in colors):
                import numpy as np

                self.team_anchor = np.asarray(colors, dtype=float)
                print(f"  takım renkleri sabitlendi: {colors}", flush=True)
        payload = frames_to_json(frames, match_id=match_id, extra={
            "video": video.name, "video_info": info,
            "home_team_external_id": home_team, "away_team_external_id": away_team,
            "summary": summary,
        })
        out_json.parent.mkdir(parents=True, exist_ok=True)
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        return summary


def _load_state(watch: Path) -> dict:
    p = watch / STATE_FILE
    if p.exists():
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return {"processed": []}


def _save_state(watch: Path, state: dict) -> None:
    with open(watch / STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)


def _segments(watch: Path) -> list[Path]:
    return sorted(p for p in watch.iterdir() if p.suffix.lower() in VIDEO_EXT and p.is_file())


def _minute_from_name(name: str, pattern: str | None) -> float | None:
    if not pattern:
        return None
    m = re.search(pattern, name)
    if not m:
        return None
    try:
        return float(m.group(1))
    except (ValueError, IndexError):
        return None


def _stable(path: Path, wait_s: float = 1.0) -> bool:
    """Dosya hâlâ yazılıyor mu? İki ölçümde boyut aynıysa hazır."""
    try:
        a = path.stat().st_size
        time.sleep(wait_s)
        return a > 0 and path.stat().st_size == a
    except OSError:
        return False


def main() -> int:
    p = argparse.ArgumentParser(description="Canlı segment izleyici → tracking_frames")
    p.add_argument("--watch", required=True, help="Segmentlerin yazıldığı klasör")
    p.add_argument("--calibration", required=True)
    p.add_argument("--match-id", type=int, required=True)
    p.add_argument("--home-team", type=int, required=True)
    p.add_argument("--away-team", type=int, required=True)
    p.add_argument("--tenant", default="t-default")
    p.add_argument("--segment-seconds", type=float, default=30.0)
    p.add_argument("--start-minute", type=float, default=0.0)
    p.add_argument("--minute-from-name", default=None,
                   help=r"Dosya adından dakika çıkaran regex, örn. 'min_(\d+)'")
    p.add_argument("--period", type=int, default=1)
    p.add_argument("--fps", type=float, default=5.0)
    p.add_argument("--track-fps", type=float, default=15.0)
    p.add_argument("--tiles", type=int, default=6)
    p.add_argument("--threshold", type=float, default=0.3)
    p.add_argument("--weights", default=None)
    p.add_argument("--ingest-python", default=default_ingest_python(),
                   help="DB ingest'i çalıştıracak yorumlayıcı (varsayılan: ana venv)")
    p.add_argument("--database-url", default=None,
                   help="Ingest alt sürecine geçilecek DATABASE_URL "
                        "(verilmezse ortamdaki/.env'deki değer kullanılır)")
    p.add_argument("--poll-seconds", type=float, default=5.0)
    p.add_argument("--once", action="store_true", help="Bekleme; mevcut segmentleri işle ve çık")
    p.add_argument("--isolate", action="store_true",
                   help="Her segmenti ayrı süreçte işle (model her seferinde yeniden "
                        "yüklenir — yavaş, ama segment çökmesi izleyiciyi etkilemez)")
    args = p.parse_args()

    watch = Path(args.watch)
    watch.mkdir(parents=True, exist_ok=True)
    out_dir = watch / "frames"
    out_dir.mkdir(exist_ok=True)
    state = _load_state(watch)
    processed: set[str] = set(state.get("processed", []))
    index = len(processed)
    retries: dict[str, int] = {}

    ingest_env = dict(os.environ)
    if args.database_url:
        ingest_env["DATABASE_URL"] = args.database_url

    warm: WarmTracker | None = None
    if not args.isolate:
        # Ağır import'lar (torch/rfdetr) yalnız sıcak yolda; --isolate'te alt süreç yükler.
        from app.tracking.detect import DetectorConfig

        warm = WarmTracker(
            calibration=args.calibration,
            detector_cfg=DetectorConfig(
                threshold=args.threshold, tiles=args.tiles, weights=args.weights,
            ),
            pipeline_kwargs={
                "fps_out": args.fps, "track_fps": args.track_fps,
                "ball_threshold": args.threshold,
            },
        )

    def _done(name: str) -> None:
        nonlocal index
        processed.add(name)
        index += 1
        _save_state(watch, {"processed": sorted(processed)})

    def _track_isolated(seg: Path, offset: float, frames_json: Path) -> bool:
        """Eski yol: her segment ayrı süreçte (model her seferinde yeniden yüklenir)."""
        cmd = [
            sys.executable, "-m", "scripts.track_video",
            "--video", str(seg), "--calibration", args.calibration,
            "--out", str(frames_json), "--match-id", str(args.match_id),
            "--home-team", str(args.home_team), "--away-team", str(args.away_team),
            "--fps", str(args.fps), "--track-fps", str(args.track_fps),
            "--tiles", str(args.tiles), "--threshold", str(args.threshold),
            "--ball-threshold", str(args.threshold),
            "--clip-offset-minutes", f"{offset:.4f}", "--period", str(args.period),
        ]
        if args.weights:
            cmd += ["--weights", args.weights]
        rc = subprocess.run(cmd, check=False).returncode  # noqa: S603 — sabit komut listesi
        if rc != 0 or not frames_json.exists():
            print(f"  {seg.name}: işlenemedi (çıkış {rc}) — atlandı", flush=True)
            return False
        return True

    def _track_warm(seg: Path, offset: float, frames_json: Path) -> bool:
        """Sıcak model: aynı süreçte, dedektör yeniden yüklenmeden."""
        assert warm is not None
        warm.run(
            seg, out_json=frames_json, offset_minutes=offset,
            match_id=args.match_id, home_team=args.home_team,
            away_team=args.away_team, period=args.period,
        )
        return frames_json.exists()

    def _handle(seg: Path) -> None:
        """Tek segment: takip → JSON → DB. İşlendi işaretlemesi burada yapılır."""
        offset = _minute_from_name(seg.name, args.minute_from_name)
        if offset is None:
            offset = args.start_minute + index * (args.segment_seconds / 60.0)
        frames_json = out_dir / f"{seg.stem}.json"
        t0 = time.time()
        ok = _track_isolated(seg, offset, frames_json) if args.isolate \
            else _track_warm(seg, offset, frames_json)
        if not ok:
            _done(seg.name)
            return
        ing = subprocess.run(  # noqa: S603 — sabit komut listesi
            [args.ingest_python, "-m", "scripts.ingest_tracking_json",
             "--json", str(frames_json), "--tenant", args.tenant,
             "--match-id", str(args.match_id), "--append"],
            capture_output=True, text=True, cwd=str(PROJECT_ROOT), check=False,
            env=ingest_env,
        )
        written = ""
        for line in ing.stdout.splitlines():
            if "frames_written" in line:
                written = line.split(":")[-1].strip()
        if ing.returncode != 0:
            # Kareler DB'ye YAZILMADI. Segmenti "işlendi" saymıyoruz: JSON diskte
            # duruyor, sonraki turda yeniden denenecek (DB geçici düşmüş olabilir).
            tries = retries.get(seg.name, 0) + 1
            retries[seg.name] = tries
            err = (ing.stderr.strip() or ing.stdout.strip())[-200:]
            if tries >= MAX_INGEST_RETRY:
                print(f"  {seg.name}: ingest {tries} kez başarısız — vazgeçildi. {err}", flush=True)
                _done(seg.name)
            else:
                print(f"  {seg.name}: ingest hatası ({tries}/{MAX_INGEST_RETRY}, "
                      f"yeniden denenecek) — {err}", flush=True)
            return
        took = time.time() - t0
        real_time = took <= args.segment_seconds
        # Isınma yalnız ilk segmentte (ya da çözünürlük değişiminde) olur;
        # gerçek zamana yetişme kararını ısınmasız süreye göre ver.
        extra = ""
        if warm is not None and warm.warmup_seconds > 0.0:
            warmup = warm.warmup_seconds
            warm.warmup_seconds = 0.0
            steady = took - warmup
            real_time = steady <= args.segment_seconds
            extra = f" (ısınma {warmup:.0f} sn hariç {steady:.0f} sn)"
        print(
            f"  {seg.name}: dk {offset:.2f}+ · {written or '?'} kare · "
            f"{took:.0f} sn{extra} "
            f"{'✓ gerçek zamana yetişiyor' if real_time else '⚠ segmentten yavaş'}",
            flush=True,
        )
        _done(seg.name)

    mode = "ayrı süreç (--isolate)" if args.isolate else "sıcak model"
    print(f"izleniyor: {watch} · maç {args.match_id} · segment {args.segment_seconds} sn"
          f" · işlenmiş {len(processed)} · mod: {mode}", flush=True)
    try:
        while True:
            new = [s for s in _segments(watch) if s.name not in processed]
            for seg in new:
                if not _stable(seg):
                    continue   # hâlâ yazılıyor, sonraki turda
                # Canlı maçta tek segmentin beklenmedik hatası tüm izleyiciyi
                # öldürmemeli: logla, o segmenti atla, akışa devam et.
                try:
                    _handle(seg)
                except KeyboardInterrupt:
                    raise
                except Exception as exc:  # noqa: BLE001 — canlı akış sürmeli
                    print(f"  {seg.name}: beklenmedik hata ({type(exc).__name__}: {exc}) "
                          f"— atlandı, akış sürüyor", flush=True)
                    _done(seg.name)
            if args.once:
                break
            time.sleep(args.poll_seconds)
    except KeyboardInterrupt:
        print("durduruldu", flush=True)
    if retries:
        print(f"uyarı: {len(retries)} segment DB'ye yazılamadı — {sorted(retries)}", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
