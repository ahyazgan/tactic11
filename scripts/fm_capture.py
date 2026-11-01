"""Football Manager 2D maç ekranından canlı takip kareleri (deneme ortamı).

FM'de maçı **2D görünümde** açın; bu betik ekranı yakalar, sahayı ve oyuncu
dairelerini bulur (`app.tracking.screen2d`), kareleri `tracking_frames`'e yazar.
Kamera WS'i (`/ws/matches/<id>/live?feed=camera`) bunları gerçek video gibi okur:
şekil bekçisi, takip sinyalleri, panel. Amaç uçtan uca canlı akışı, uyarıların
zamanlamasını ve panel deneyimini gerçek maç beklemeden denemektir; gerçek video
doğruluğu hakkında bir şey KANITLAMAZ (ışık, gölge, kamera titremesi yok).

Önce tek ekran görüntüsüyle ayar (renkler/saha doğru bulunuyor mu):

    python -m scripts.fm_capture --image fm.png --debug fm_debug.png --home-color "#d22828"

Canlı:

    python -m scripts.fm_capture --match-id 995001 --home-team 1 --away-team 2 \\
        --region 0,0,1920,1080 --fps 5 --speed 6 --home-color "#d22828"

`--speed`: FM'de bir gerçek dakikada kaç maç dakikası geçtiği (FM maç hızı).
Maç saati ekrandan okunmaz; yakalama süresi × hız ile ilerler. Devre arasında
yakalamayı durdurup ikinci yarıda `--start-minute 45` ile yeniden başlatın.
Kimlik takibi yok: her karede oyuncular sentetik kimlik alır (şekil motorları
kimlik istemez). Kaynak etiketi `screen_capture` (sürekli takip sayılır).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np

from app.domain import PlayerPosition, TrackingFrame
from app.tracking.screen2d import (
    Detection,
    PitchRect,
    TeamPalette,
    detect,
    find_pitch,
    nearest_owner,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE = "screen_capture"
POSSESSION_HOLD_S = 2.0       # top görünmezken son sahip bu kadar (gerçek sn) korunur
PITCH_REDETECT_EVERY = 100    # kare; pencere taşınırsa saha yeniden bulunur
SYNTHETIC_ID_BASE = 40000


def parse_hex(color: str | None) -> tuple[float, float, float] | None:
    if not color:
        return None
    c = color.lstrip("#")
    if len(c) != 6:
        raise ValueError(f"renk #rrggbb olmalı: {color}")
    return float(int(c[0:2], 16)), float(int(c[2:4], 16)), float(int(c[4:6], 16))


@dataclass
class CaptureClock:
    """Yakalama süresinden maç dakikası; FM ekrandaki saat okunmaz."""

    start_minute: float = 0.0
    speed: float = 1.0
    started: float = field(default_factory=time.monotonic)

    def minute(self, now: float) -> float:
        return self.start_minute + (now - self.started) / 60.0 * self.speed


@dataclass
class FrameBuilder:
    """Algılama → TrackingFrame; sahipliği kısa süre tutar."""

    match_id: int
    home_team: int
    away_team: int
    kickoff_wall: datetime = field(default_factory=lambda: datetime.now(UTC))
    _owner: int | None = None
    _owner_seen: float | None = None

    def build(self, det: Detection, minute: float, now: float) -> TrackingFrame:
        ids = (self.home_team, self.away_team)
        owner = nearest_owner(det)
        if owner is not None:
            self._owner, self._owner_seen = owner, now
        elif self._owner_seen is not None and now - self._owner_seen > POSSESSION_HOLD_S:
            self._owner = None
        players = tuple(
            PlayerPosition(player_external_id=SYNTHETIC_ID_BASE + i, x=x, y=y,
                           team_external_id=ids[t] if t is not None else None, identity_estimated=True)
            for i, (t, x, y) in enumerate(det.players))
        ball = PlayerPosition(player_external_id=0, x=det.ball[0], y=det.ball[1]) if det.ball else None
        return TrackingFrame(
            sport="football", match_external_id=self.match_id,
            timestamp=self.kickoff_wall + timedelta(minutes=minute), period=1 if minute < 45 else 2,
            minute=round(minute, 4), ball=ball, players=players, source=SOURCE,
            possession_team_external_id=ids[self._owner] if self._owner is not None else None)


def grab(region: tuple[int, int, int, int] | None) -> np.ndarray:
    from PIL import ImageGrab  # noqa: PLC0415 — yalnız canlı yakalamada

    bbox = None if region is None else (region[0], region[1], region[0] + region[2], region[1] + region[3])
    return np.asarray(ImageGrab.grab(bbox=bbox, all_screens=True).convert("RGB"))


def load_image(path: str) -> np.ndarray:
    from PIL import Image  # noqa: PLC0415

    return np.asarray(Image.open(path).convert("RGB"))


def save_debug(rgb: np.ndarray, det: Detection, palette: TeamPalette, path: str) -> None:
    """Algılananları görüntü üstüne çiz: saha kutusu, takım renginde halka, top."""
    from PIL import Image, ImageDraw  # noqa: PLC0415

    img = Image.fromarray(rgb.copy())
    d = ImageDraw.Draw(img)
    r = det.pitch
    d.rectangle([r.x0, r.y0, r.x1, r.y1], outline=(255, 255, 0), width=2)
    marks = {0: (255, 80, 80), 1: (80, 160, 255), None: (255, 255, 255)}
    for team, x, y in det.players:
        cx, cy = r.x0 + x / 100 * r.width, r.y0 + y / 100 * r.height
        d.ellipse([cx - 11, cy - 11, cx + 11, cy + 11], outline=marks[team], width=3)
    if det.ball:
        bx, by = r.x0 + det.ball[0] / 100 * r.width, r.y0 + det.ball[1] / 100 * r.height
        d.ellipse([bx - 6, by - 6, bx + 6, by + 6], outline=(255, 0, 255), width=3)
    img.save(path)


def summarize(det: Detection, palette: TeamPalette) -> str:
    counts = {0: 0, 1: 0, None: 0}
    for t, _x, _y in det.players:
        counts[t] += 1
    colors = ("-" if palette.centers is None else
              " / ".join("#" + "".join(f"{int(v):02x}" for v in c) for c in palette.centers))
    return (f"saha {det.pitch.width}×{det.pitch.height} px @({det.pitch.x0},{det.pitch.y0}) · "
            f"ev {counts[0]} · dep {counts[1]} · atanmamış {counts[None]} · "
            f"top {'var' if det.ball else 'yok'} · takım renkleri {colors}")


def ingest(json_path: Path, args: argparse.Namespace) -> subprocess.Popen:
    from scripts.track_live import default_ingest_python  # noqa: PLC0415

    cmd = [args.ingest_python or default_ingest_python(), "-m", "scripts.ingest_tracking_json",
           "--json", str(json_path), "--tenant", args.tenant, "--match-id", str(args.match_id), "--append"]
    return subprocess.Popen(cmd, cwd=str(PROJECT_ROOT), stdout=subprocess.DEVNULL)  # noqa: S603


def write_chunk(frames: list[TrackingFrame], out_dir: Path, index: int, args: argparse.Namespace) -> Path:
    from app.tracking.frames import frames_to_json  # noqa: PLC0415

    path = out_dir / f"chunk_{index:05d}.json"
    payload = frames_to_json(frames, match_id=args.match_id, source_name=SOURCE,
                             extra={"home_team_external_id": args.home_team,
                                    "away_team_external_id": args.away_team})
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    tmp.replace(path)
    return path


def parse_region(text: str | None) -> tuple[int, int, int, int] | None:
    if not text:
        return None
    parts = [int(v) for v in text.split(",")]
    if len(parts) != 4:
        raise ValueError("--region x,y,genişlik,yükseklik")
    return parts[0], parts[1], parts[2], parts[3]


def main() -> int:
    p = argparse.ArgumentParser(description="FM 2D ekranı → canlı takip kareleri")
    p.add_argument("--image", default=None, help="tek ekran görüntüsünü ayrıştır (ayar için) ve çık")
    p.add_argument("--debug", default=None, help="algılananları çizdiği PNG")
    p.add_argument("--region", default=None, help="yakalanacak ekran bölgesi x,y,w,h (varsayılan tüm ekran)")
    p.add_argument("--pitch-rect", default=None, help="saha dikdörtgeni x0,y0,x1,y1 (bölge içinde; otomatik yerine)")
    p.add_argument("--home-color", default=None, help="ev sahibi daire rengi #rrggbb (takım sırası için)")
    p.add_argument("--swap-teams", action="store_true", help="ev/deplasman renklerini değiştir")
    p.add_argument("--match-id", type=int, default=995001)
    p.add_argument("--home-team", type=int, default=1)
    p.add_argument("--away-team", type=int, default=2)
    p.add_argument("--tenant", default="t-default")
    p.add_argument("--fps", type=float, default=5.0)
    p.add_argument("--speed", type=float, default=1.0, help="gerçek dakika başına maç dakikası (FM hızı)")
    p.add_argument("--start-minute", type=float, default=0.0)
    p.add_argument("--chunk-seconds", type=float, default=10.0, help="bu sıklıkla DB'ye yazılır")
    p.add_argument("--out-dir", default=None)
    p.add_argument("--ingest-python", default=None)
    p.add_argument("--max-seconds", type=float, default=None, help="bu kadar sonra dur (deneme)")
    args = p.parse_args()

    palette = TeamPalette(home_hint=parse_hex(args.home_color), swap=args.swap_teams)
    fixed = None
    if args.pitch_rect:
        x0, y0, x1, y1 = (int(v) for v in args.pitch_rect.split(","))
        fixed = PitchRect(x0, y0, x1, y1)

    if args.image:
        rgb = load_image(args.image)
        t0 = time.perf_counter()
        det = detect(rgb, palette, fixed)
        took = (time.perf_counter() - t0) * 1000
        if det is None:
            print("saha bulunamadı — FM 2D görünümde mi? --pitch-rect ile elle verin.")
            return 1
        print(f"{summarize(det, palette)} · {took:.0f} ms")
        if args.debug:
            save_debug(rgb, det, palette, args.debug)
            print(f"çizim: {args.debug}")
        return 0

    region = parse_region(args.region)
    out_dir = Path(args.out_dir) if args.out_dir else PROJECT_ROOT / "data" / "tracking" / "fm" / str(args.match_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    clock = CaptureClock(start_minute=args.start_minute, speed=args.speed)
    builder = FrameBuilder(args.match_id, args.home_team, args.away_team)
    buffer: list[TrackingFrame] = []
    chunk_index, frames_total, last_flush = 0, 0, time.monotonic()
    pending: subprocess.Popen | None = None
    rect = fixed
    period = 1.0 / max(args.fps, 0.1)
    print(f"[fm] yakalanıyor: bölge {region or 'tüm ekran'} · {args.fps:g} fps · hız ×{args.speed:g} · "
          f"maç {args.match_id} → panel: /ws/matches/{args.match_id}/live?feed=camera&my_team_id={args.home_team}",
          flush=True)
    try:
        while True:
            tick = time.monotonic()
            if args.max_seconds is not None and tick - clock.started > args.max_seconds:
                break
            rgb = grab(region)
            if rect is None or (fixed is None and frames_total % PITCH_REDETECT_EVERY == 0):
                rect = find_pitch(rgb) or rect
            det = detect(rgb, palette, rect) if rect is not None else None
            if det is None:
                print("[fm] saha görünmüyor — FM 2D görünümde mi?", flush=True)
                time.sleep(1.0)
                continue
            buffer.append(builder.build(det, clock.minute(tick), tick))
            frames_total += 1
            if frames_total == 1:
                print(f"[fm] ilk kare: {summarize(det, palette)}", flush=True)
            if tick - last_flush >= args.chunk_seconds and buffer:
                if pending is not None:
                    pending.wait()
                path = write_chunk(buffer, out_dir, chunk_index, args)
                pending = ingest(path, args)
                print(f"[fm] dk {buffer[-1].minute:.1f} · {len(buffer)} kare yazılıyor · {summarize(det, palette)}",
                      flush=True)
                buffer, chunk_index, last_flush = [], chunk_index + 1, tick
            time.sleep(max(0.0, period - (time.monotonic() - tick)))
    except KeyboardInterrupt:
        print("[fm] durduruldu", flush=True)
    if buffer:
        if pending is not None:
            pending.wait()
        pending = ingest(write_chunk(buffer, out_dir, chunk_index, args), args)
    if pending is not None:
        pending.wait()
    print(f"[fm] toplam {frames_total} kare", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
