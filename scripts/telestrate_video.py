"""Takip çıktısı + video → otomatik telestrasyonlu video (venv-cv; opencv + pillow).

Takip hattından (`scripts/track_video.py`) SONRA çalışır, onu değiştirmez:

    venv-cv\\Scripts\\python.exe -m scripts.telestrate_video \\
        --video clip.mp4 --calibration calib.json --frames frames.json \\
        --out tele.mp4 --home-attack x+ --marks-json marks.json

Oyuncu halkaları, savunan takımın blok çizgileri ve faz etiketi
(app/tracking/telestration.py) kaynak videonun aynı anına çizilir. Varsayılan
olarak çıktı kaynak kare hızındadır: takip kareleri (~5 fps) arasında oyuncular
kimliğe göre doğrusal enterpole edilir; kamera kesmesinde (continuity_id) ya da
0,6 sn'den uzun boşlukta enterpolasyon yapılmaz. `--no-interpolate` yalnız takip
karelerini yazar. `--marks-json` çizim öğelerini yazılan her kare için verir.

Sınır: yalnız sabit kalibrasyon (sabit kamera). Kare başına kalibrasyonla
işlenmiş hareketli kamera çıktısı karelerin kendi homografisini taşımadığı
için desteklenmez.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from app.domain import TrackingFrame
from app.tracking.calibration import PitchCalibration
from app.tracking.telestration import (
    INTERPOLATE_MAX_GAP_S,
    MAX_REPROJECTION_M,
    PlayerSpot,
    Telestrator,
    calibration_validation,
    interpolate_point,
    interpolate_spots,
    render,
    scaled,
    spots_from_frame,
)

HOME_ATTACK = {"auto": 0, "x+": 1, "x-": -1}


def output_size(width: int, height: int, max_width: int) -> tuple[int, int]:
    """Kodek uyumlu çift boyutlar."""
    scale = min(1.0, max_width / max(width, 1))
    return max(2, int(width * scale) // 2 * 2), max(2, round(height * scale / 2) * 2)


Spots = tuple[list[PlayerSpot], tuple[float, float] | None, int | None]


def schedule(seconds: list[float], spots: list[Spots], continuity: list[int | None], src_fps: float,
             interpolate: bool) -> list[tuple[int, float, Spots]]:
    """Yazılacak video kareleri: (kare no, sn, (oyuncular, top, sahip)).

    Enterpolasyonsuz: her takip karesi en yakın video karesine (aynı kareye düşen
    ikincisi atlanır). Enterpolasyonlu: ilk ile son takip karesi arasındaki her video
    karesi; aynı süreklilikte ve kısa aralıklı iki takip karesi arasında doğrusal,
    aksi halde yalnız takip karesinin yarım adım yakınında, değilse çizimsiz (None).
    """
    if not interpolate:
        out, last = [], -1
        for t, sp in zip(seconds, spots, strict=True):
            idx = round(t * src_fps)
            if idx > last:
                out.append((idx, t, sp))
                last = idx
        return out
    out, k = [], 0
    for idx in range(round(seconds[0] * src_fps), round(seconds[-1] * src_fps) + 1):
        t = idx / src_fps
        while k + 1 < len(seconds) and seconds[k + 1] <= t:
            k += 1
        a = spots[k]
        if k + 1 < len(seconds):
            gap = seconds[k + 1] - seconds[k]
            if 0 < gap <= INTERPOLATE_MAX_GAP_S and continuity[k] == continuity[k + 1]:
                w = min(1.0, max(0.0, (t - seconds[k]) / gap))
                b = spots[k + 1]
                out.append((idx, t, (interpolate_spots(a[0], b[0], w), interpolate_point(a[1], b[1], w),
                                     a[2] if w < 0.5 else b[2])))
                continue
        if abs(t - seconds[k]) <= 0.5 / src_fps:
            out.append((idx, t, a))
    return out


class VideoSink:
    """mp4 yazıcı: tarayıcıda oynatılabilen H.264 (PyAV/libx264) istenirse ve varsa onu, yoksa OpenCV mp4v."""

    def __init__(self, path: str | Path, fps: float, size: tuple[int, int], *, h264: bool = False) -> None:
        self._av: tuple | None = None
        self._cv = None
        if h264:
            try:
                import av

                container = av.open(str(path), "w")
                stream = container.add_stream("libx264", rate=round(fps))
                stream.width, stream.height = size
                stream.pix_fmt, stream.options = "yuv420p", {"crf": "23", "preset": "veryfast"}
                self._av = (av, container, stream)
            except Exception:  # noqa: BLE001 — kodek yoksa mp4v ile devam
                self._av = None
        if self._av is None:
            import cv2

            self._cv = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, size)
            if not self._cv.isOpened():
                raise OSError(f"video yazıcısı açılamadı: {path}")

    @property
    def codec(self) -> str:
        return "h264" if self._av is not None else "mp4v"

    def write(self, bgr) -> None:
        if self._av is not None:
            av, container, stream = self._av
            for packet in stream.encode(av.VideoFrame.from_ndarray(bgr, format="bgr24")):
                container.mux(packet)
        elif self._cv is not None:
            self._cv.write(bgr)

    def close(self) -> None:
        if self._av is not None:
            _av, container, stream = self._av
            for packet in stream.encode():
                container.mux(packet)
            container.close()
        elif self._cv is not None:
            self._cv.release()


def warn_calibration(calib: PitchCalibration) -> None:
    source, error = calibration_validation(calib)
    if source == "unverified":
        print("uyarı: kalibrasyon bağımsız doğrulanmamış (noktalar saha işareti değil, çizgi doğrulaması "
              "yok); yalnız halkalar çizilecek. Saha çizgisi noktalarıyla kalibrasyon kurun.", file=sys.stderr)
    elif error is not None and error > MAX_REPROJECTION_M:
        print(f"uyarı: kalibrasyon hatası {error:.2f} m > {MAX_REPROJECTION_M} m; yalnız halkalar çizilecek.",
              file=sys.stderr)


def render_segment(video: str | Path, payload: dict, calib: PitchCalibration, out: str | Path, *,
                   home_attack: int = 0, tele: Telestrator | None = None, clip_offset_minutes: float | None = None,
                   width: int = 1600, interpolate: bool = True, keep_marks: bool = False,
                   h264: bool = False) -> tuple[dict, list[dict], Telestrator]:
    """Bir videoyu takip çıktısıyla telestrasyonlu yaz → (özet, kare başına öğeler, telestratör).

    `tele` verilirse durumu (yön, sahiplik, hat yumuşatma, etiket) korunarak devam
    edilir — canlı modda segmentler arası süreklilik için. `clip_offset_minutes`
    verilmezse videonun başı ilk takip karesinin dakikası sayılır (canlı segment)."""
    import cv2

    frames = sorted((TrackingFrame.model_validate(f) for f in payload["frames"]), key=lambda f: f.minute)
    if len(frames) < 2:
        raise ValueError("en az iki takip karesi gerekli")
    home, away = payload["home_team_external_id"], payload["away_team_external_id"]
    offset = frames[0].minute if clip_offset_minutes is None else clip_offset_minutes
    seconds = [(f.minute - offset) * 60.0 for f in frames]
    steps = sorted(b - a for a, b in zip(seconds, seconds[1:], strict=False) if b > a)
    fps = 1.0 / steps[len(steps) // 2]
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise OSError(f"video açılamadı: {video}")
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    size = output_size(int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)), width)
    out_fps = src_fps if interpolate else fps
    try:
        sink = VideoSink(out, out_fps, size, h264=h264)
    except OSError:
        cap.release()
        raise
    spots = [spots_from_frame(f, home, away, calib) for f in frames]
    plan = schedule(seconds, spots, [f.continuity_id for f in frames], src_fps, interpolate)
    tele = tele or Telestrator(out_fps, home_attack)
    before = dict(tele.gate_counts)
    log: list[dict] = []
    position = written = 0
    try:
        for idx, t, (players, ball, owner) in plan:
            while position < idx and cap.grab():
                position += 1
            ok, bgr = cap.read()
            if not ok:
                break
            position += 1
            marks = tele.marks(players, ball, calib, owner)
            factor = size[0] / bgr.shape[1]
            if (bgr.shape[1], bgr.shape[0]) != size:
                # önce küçült, sonra çiz: 4K karede çizmek gerçek zamanın ~3 katı sürüyordu
                bgr = cv2.resize(bgr, size, interpolation=cv2.INTER_AREA)
            render(bgr, scaled(marks, factor))
            sink.write(bgr)
            written += 1
            if keep_marks:
                log.append({"seconds": round(t, 3), "minute": round(offset + t / 60.0, 4),
                            "marks": [asdict(m) for m in marks]})
    finally:
        sink.close()
        cap.release()
    gates = {k: v - before.get(k, 0) for k, v in tele.gate_counts.items() if v - before.get(k, 0)}
    summary = {"frames_written": written, "fps": round(out_fps, 3), "tracking_fps": round(fps, 3),
               "interpolated": interpolate, "codec": sink.codec, "start_minute": round(offset, 4),
               "gates": gates, "drawn_ratio": round(gates.get("drawn", 0) / max(written, 1), 3),
               "label": tele.label}
    return summary, log, tele


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--video", required=True)
    p.add_argument("--calibration", required=True, help="Takipte kullanılan sabit kalibrasyon JSON")
    p.add_argument("--frames", required=True, help="scripts.track_video çıktısı (frames JSON)")
    p.add_argument("--out", required=True, help="Telestrasyonlu mp4")
    p.add_argument("--home-attack", default="auto", choices=sorted(HOME_ATTACK),
                   help="Ev sahibi kalibrasyonun saha x'i artan (x+) ya da azalan (x-) yöne hücum eder; "
                        "auto = kaleci/en derin oyuncudan çıkar")
    p.add_argument("--clip-offset-minutes", type=float, default=0.0,
                   help="Takipte verilen klip başlangıç dakikası (track_video ile aynı)")
    p.add_argument("--width", type=int, default=1600, help="Çıktı genişliği (en fazla)")
    p.add_argument("--marks-json", default=None, help="Kare başına çizim öğeleri JSON yolu")
    p.add_argument("--no-interpolate", action="store_true", help="Yalnız takip karelerini yaz (~5 fps)")
    p.add_argument("--h264", action="store_true", help="Tarayıcıda oynatılabilen H.264 (PyAV) ile yaz")
    args = p.parse_args()

    calib = PitchCalibration.load(args.calibration)
    warn_calibration(calib)
    payload = json.loads(Path(args.frames).read_text(encoding="utf-8"))
    try:
        summary, log, _tele = render_segment(
            args.video, payload, calib, args.out, home_attack=HOME_ATTACK[args.home_attack],
            clip_offset_minutes=args.clip_offset_minutes, width=args.width,
            interpolate=not args.no_interpolate, keep_marks=bool(args.marks_json), h264=args.h264)
    except (OSError, ValueError) as exc:
        print(f"hata: {exc}", file=sys.stderr)
        return 2
    summary["home_attack"] = args.home_attack
    if args.marks_json:
        Path(args.marks_json).write_text(json.dumps({"summary": summary, "frames": log}, ensure_ascii=False),
                                         encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if summary["frames_written"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
