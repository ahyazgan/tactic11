"""Canlı maç modu: kaynak ver (dosya / RTSP / HTTP akışı), gerisi otomatik (venv-cv).

## Neden bu script var

Parçalar vardı ama tek komut yoktu: kamera segment yazar (ffmpeg, README'de
örnek), `track_live` klasörü izler, panel kareleri okur. Kullanıcı üç şey
istiyor: kendi kamerası, stadyum kamerası (RTSP), canlı yayın. Üçü de aynı
hatta iner; fark yalnız girişte. Bu script girişi tek komuta indirir ve
GECİKMEYİ ÖLÇÜP GÖSTERİR — gizlemez.

    venv-cv\\Scripts\\python.exe -m scripts.canli_mac --source mac.mp4 \\
        --match-id 990201 --home-team 611 --away-team 612 [--calibration saha.json]
    venv-cv\\Scripts\\python.exe -m scripts.canli_mac --source rtsp://kamera/stream ...
    venv-cv\\Scripts\\python.exe -m scripts.canli_mac --source https://.../index.m3u8 ...

## Dosya kaynağı = canlı prova

Dosya verildiğinde ffmpeg `-re` ile GERÇEK HIZDA okur: 90 dakikalık maç 90
dakikada akar, segmentler maç saatinde düşer. Böylece "sistem canlı maça
yetişiyor mu, kaç dakika geriden geliyor" dürüstçe ölçülür; kamera almadan
önce cevap bu ölçümden gelir. `--no-realtime` ile dosya olabildiğince hızlı
işlenir (maç sonrası analiz).

## Gecikme nasıl ölçülür

Her turda iki saat karşılaştırılır: akışın maç saati (dosyada: geçen duvar
saati; akışta: yazılan segment sayısı) ve panelin gördüğü son kare (işlenen
segment sayısı). Fark = koçun gördüğü resmin kaç saniye eski olduğu. Ekrana
`[canlı] işlenen dk 63.0 · akış dk 66.5 · gecikme 210 sn` yazılır.

## Sınırlar (dürüst)

- Gecikme ilk kurulumda dakikalar mertebesindedir (geniş açıda dilimli tespit
  gerçek zamanın ~4 katı yavaş — README "Canlı takip performansı"). Devre arası
  ve 60-80. dk kararları için yeterli, 89. dk için değil.
- Sabit kamera için kalibrasyon JSON'u gerekir (`scripts.propose_calibration`);
  verilmezse çapa görüntüden aranır (TV kuralı) — sabit kamerada yanlış olabilir.
- Skor ve dakika videodan okunmaz; dakika segment sırasından türetilir
  (`--start-minute`), skor panelde şut olaylarından gelir.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SEGMENT_SECONDS = 30.0
POLL_SECONDS = 5.0
STREAM_SCHEMES = ("rtsp://", "rtsps://", "rtmp://", "http://", "https://", "udp://", "srt://")


@dataclass(frozen=True)
class SourceKind:
    is_stream: bool
    realtime: bool          # dosyayı gerçek hızda oku (-re)
    label: str


def classify_source(source: str, *, realtime_file: bool) -> SourceKind:
    low = source.lower()
    if low.startswith(STREAM_SCHEMES):
        return SourceKind(is_stream=True, realtime=False, label="akış")
    return SourceKind(is_stream=False, realtime=realtime_file,
                      label="dosya (canlı prova)" if realtime_file else "dosya (hızlı)")


def find_ffmpeg(explicit: str | None = None) -> str:
    """ffmpeg yolu: verilen → PATH → imageio-ffmpeg statik ikilisi. Yoksa hata."""
    if explicit:
        return explicit
    on_path = shutil.which("ffmpeg")
    if on_path:
        return on_path
    try:
        import imageio_ffmpeg  # noqa: PLC0415 — isteğe bağlı bağımlılık
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError as e:
        raise SystemExit(
            "ffmpeg bulunamadı. Kur: `winget install Gyan.FFmpeg` ya da "
            "`venv-cv\\Scripts\\pip install imageio-ffmpeg`"
        ) from e


def ffmpeg_segment_command(
    ffmpeg: str, source: str, kind: SourceKind, watch: Path, *,
    segment_seconds: float, start_seconds: float = 0.0, transcode: bool = False,
    height: int | None = None,
) -> list[str]:
    """Kaynağı `watch/seg_%04d.mp4` segmentlerine böl.

    `-c copy` (H.264 kaynak) kayıpsız ve ucuzdur; VP9/webm ya da çözünürlük
    düşürme istenirse yeniden kodlanır (`transcode`, `height`). Segmentler
    anahtar kareye hizalanır; `-reset_timestamps 1` her segmenti 0'dan başlatır
    ki takip kare zamanlarını segment içi saysın.
    """
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "warning", "-nostdin"]
    if kind.is_stream and source.lower().startswith(("rtsp://", "rtsps://")):
        cmd += ["-rtsp_transport", "tcp"]
    if kind.realtime:
        cmd += ["-re"]
    if start_seconds > 0:
        cmd += ["-ss", f"{start_seconds:.3f}"]
    cmd += ["-i", source, "-an"]
    if transcode or height:
        cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                "-g", str(int(segment_seconds * 2)), "-pix_fmt", "yuv420p"]
        if height:
            cmd += ["-vf", f"scale=-2:{int(height)}"]
        cmd += ["-force_key_frames", f"expr:gte(t,n_forced*{segment_seconds:g})"]
    else:
        cmd += ["-c:v", "copy"]
    cmd += ["-f", "segment", "-segment_time", f"{segment_seconds:g}",
            "-reset_timestamps", "1", "-segment_format", "mp4",
            str(watch / "seg_%04d.mp4")]
    return cmd


def source_needs_transcode(source: str) -> bool:
    """H.264 değilse (VP9/AV1/HEVC…) mp4 segment için yeniden kodla."""
    try:
        import cv2  # noqa: PLC0415
    except ImportError:
        return False
    cap = cv2.VideoCapture(source)
    try:
        code = int(cap.get(cv2.CAP_PROP_FOURCC))
    finally:
        cap.release()
    fourcc = "".join(chr((code >> (8 * i)) & 0xFF) for i in range(4)).strip("\x00").lower()
    return fourcc not in {"avc1", "h264", "x264"}


@dataclass(frozen=True)
class Latency:
    processed_minute: float
    stream_minute: float
    lag_seconds: float


def latency(processed_segments: int, written_segments: int, *, segment_seconds: float,
            start_minute: float, elapsed_seconds: float | None) -> Latency:
    """Gecikme = akışın maç saati − panelin gördüğü son kare.

    Akış saati: dosya provasında geçen duvar saati (gerçek hız); akışta yazılan
    segment sayısı (duvar saati bilinmez, kamera ne yazdıysa o).
    """
    processed = start_minute + processed_segments * segment_seconds / 60.0
    if elapsed_seconds is not None:
        stream = start_minute + elapsed_seconds / 60.0
    else:
        stream = start_minute + written_segments * segment_seconds / 60.0
    return Latency(
        processed_minute=round(processed, 2), stream_minute=round(stream, 2),
        lag_seconds=round(max(0.0, (stream - processed) * 60.0), 1),
    )


def _processed_count(watch: Path) -> int:
    state = watch / ".track_live_state.json"
    if not state.is_file():
        return 0
    try:
        return len(json.loads(state.read_text(encoding="utf-8")).get("processed", []))
    except (ValueError, OSError):
        return 0


def _written_count(watch: Path) -> int:
    return len(list(watch.glob("seg_*.mp4")))


def main() -> int:
    p = argparse.ArgumentParser(description="Canlı maç modu: kaynak → segment → takip → panel")
    p.add_argument("--source", required=True, help="video dosyası | rtsp://... | http(s)://... (HLS)")
    p.add_argument("--match-id", type=int, required=True)
    p.add_argument("--home-team", type=int, required=True)
    p.add_argument("--away-team", type=int, required=True)
    p.add_argument("--tenant", default="t-default")
    p.add_argument("--watch", default=None, help="segment klasörü (varsayılan data/tracking/live/<match-id>)")
    p.add_argument("--calibration", default=None, help="sabit kamera için saha kalibrasyon JSON'u")
    p.add_argument("--segment-seconds", type=float, default=DEFAULT_SEGMENT_SECONDS)
    p.add_argument("--start-minute", type=float, default=0.0, help="akışın başladığı maç dakikası")
    p.add_argument("--start-seconds", type=float, default=0.0, help="dosyada bu saniyeden başla")
    p.add_argument("--no-realtime", action="store_true", help="dosyayı gerçek hızda değil, olabildiğince hızlı oku")
    p.add_argument("--height", type=int, default=None, help="segmentleri bu yüksekliğe indir (ör. 1080)")
    p.add_argument("--ffmpeg", default=None)
    p.add_argument("--camera", default="auto", choices=["auto", "static", "broadcast", "operated"],
                   help="static=sabit, broadcast=TV, operated=operatörlü tek kamera (pan/zoom, kesme yok)")
    p.add_argument("--tiles", type=int, default=4)
    p.add_argument("--track-fps", type=float, default=15.0)
    p.add_argument("--weights", default=None)
    p.add_argument("--backend", default="auto", choices=["auto", "torch", "onnx"])
    p.add_argument("--onnx-model", default=None)
    p.add_argument("--database-url", default=None)
    p.add_argument("--fresh", action="store_true", help="klasördeki eski segment ve durumu sil")
    args = p.parse_args()

    kind = classify_source(args.source, realtime_file=not args.no_realtime)
    if not kind.is_stream and not Path(args.source).is_file():
        print(f"kaynak yok: {args.source}")
        return 2
    watch = Path(args.watch) if args.watch else PROJECT_ROOT / "data" / "tracking" / "live" / str(args.match_id)
    if args.fresh and watch.exists():
        shutil.rmtree(watch)
    watch.mkdir(parents=True, exist_ok=True)

    ffmpeg = find_ffmpeg(args.ffmpeg)
    transcode = (not kind.is_stream) and source_needs_transcode(args.source)
    seg_cmd = ffmpeg_segment_command(
        ffmpeg, args.source, kind, watch, segment_seconds=args.segment_seconds,
        start_seconds=args.start_seconds, transcode=transcode, height=args.height,
    )
    track_cmd = [
        sys.executable, "-m", "scripts.track_live",
        "--watch", str(watch), "--match-id", str(args.match_id),
        "--home-team", str(args.home_team), "--away-team", str(args.away_team),
        "--tenant", args.tenant, "--segment-seconds", f"{args.segment_seconds:g}",
        "--start-minute", f"{args.start_minute:g}", "--camera", args.camera,
        "--tiles", str(args.tiles), "--track-fps", f"{args.track_fps:g}",
        "--backend", args.backend, "--poll-seconds", f"{POLL_SECONDS:g}",
    ]
    for flag, val in (("--calibration", args.calibration), ("--weights", args.weights),
                      ("--onnx-model", args.onnx_model), ("--database-url", args.database_url)):
        if val:
            track_cmd += [flag, val]

    print(f"[canlı] kaynak: {kind.label} · {args.source}")
    print(f"[canlı] segment: {args.segment_seconds:g} sn → {watch}"
          f"{' · yeniden kodlama' if transcode or args.height else ' · kopya'}")
    print(f"[canlı] panel: /admin/matches/{args.match_id}/live-decision?my_team_id={args.home_team}"
          f"&current_minute=<işlenen dk>")
    t0 = time.time()
    seg_proc = subprocess.Popen(seg_cmd, cwd=str(PROJECT_ROOT))  # noqa: S603
    track_proc = subprocess.Popen(track_cmd, cwd=str(PROJECT_ROOT),  # noqa: S603
                                  env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    try:
        while True:
            time.sleep(POLL_SECONDS)
            elapsed = (time.time() - t0) if kind.realtime else None
            lat = latency(_processed_count(watch), _written_count(watch),
                          segment_seconds=args.segment_seconds, start_minute=args.start_minute,
                          elapsed_seconds=elapsed)
            print(f"[canlı] işlenen dk {lat.processed_minute:.1f} · akış dk {lat.stream_minute:.1f} "
                  f"· gecikme {lat.lag_seconds:.0f} sn", flush=True)
            if seg_proc.poll() is not None and _processed_count(watch) >= _written_count(watch):
                print("[canlı] kaynak bitti ve bütün segmentler işlendi.")
                break
            if track_proc.poll() is not None:
                print(f"[canlı] izleyici durdu (kod {track_proc.returncode}).")
                break
    except KeyboardInterrupt:
        print("\n[canlı] durduruluyor…")
    finally:
        for proc in (seg_proc, track_proc):
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
    return 0


if __name__ == "__main__":
    sys.exit(main())
