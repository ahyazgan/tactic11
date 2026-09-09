"""Video → TrackingFrame hattı (venv-cv işçisi).

Akış:
1. Videoyu `track_fps` hızında örnekle (cv2) — takip için yüksek (15 fps):
   küçük/hızlı oyuncularda ardışık kareler arası IoU eşleşmesi ancak böyle tutar
2. Her karede RF-DETR ile oyuncu/top tespiti (dilimli, batch); saha dışı elenir
3. ByteTrack ile takip kimliği (supervision)
4. Top: dilimli tespit yoksa son bilinen konum çevresinde küçük, yüksek
   çözünürlüklü pencerede yeniden ara; ≤ `ball_gap_seconds` boşlukları enterpole et
5. Forma rengi biriktir → klip sonunda takım kümeleme
6. Hız: ardışık örneklerden merkezi fark (m/s), oyuncu ve top
7. `fps_out` hızında TrackingFrame üret — kalibrasyon homografisiyle
8. (opsiyonel) Etiketli önizleme videosu (çıktı fps'inde) — görsel doğrulama

Çıktı JSON'u `scripts/ingest_tracking_json.py` ile DB'ye alınır.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from app.domain.tracking import TrackingFrame
from app.tracking.calibration import PitchCalibration
from app.tracking.detect import DetectorConfig, RFDetrDetector
from app.tracking.frames import BallObservation, TrackObservation, build_frame
from app.tracking.teams import TeamAssigner, torso_color

MAX_PLAYER_SPEED_MPS = 12.0
MAX_BALL_SPEED_MPS = 45.0


@dataclass
class PipelineConfig:
    fps_out: float = 5.0
    track_fps: float = 15.0
    max_seconds: float | None = None
    detector: DetectorConfig = field(default_factory=DetectorConfig)
    track_activation_threshold: float = 0.25
    lost_track_seconds: float = 1.5
    min_track_seconds: float = 0.4
    pitch_margin_m: float = 2.0     # saha dışı tespit eleme marjı (takipten önce)
    ball_threshold: float = 0.4     # top için ayrı (daha sıkı) güven eşiği
    ball_roi_px: int = 320          # kayıp topu arama penceresi genişliği (yükseklik = 9/16)
    ball_gap_seconds: float = 1.0   # bu kadar boşluk enterpole edilir
    clip_offset_minutes: float = 0.0
    period: int = 1
    # Karelere yazılacak kaynak etiketi. Kamera hareketliyse (yayın) buraya
    # "broadcast_tracking" gelir ve motorlar kareleri top-merkezli sayar —
    # sabit homografi geçersiz olduğu için şekil/bölge analizi kapanır.
    source_name: str = "video_tracking"
    # Kamera hareketliyse (yayın) her karede homografi yeniden bulunur; oturmayan
    # kareler ATLANIR (sahte konum üretmektense kare kaybetmek yeğdir).
    per_frame_calibration: bool = False
    # TV YAYINI İÇİN ŞART. Yayın sürekli kamera değiştirir; her kesmede
    # süreklilik kopar. Bu kapalıyken kalibratör ilk kesmede KAYIP durumuna
    # düşer ve bir daha ASLA toparlanmaz — segmentin kalanındaki her kare atılır.
    # Açıkken kesme sonrası ÇAPADAN aranır (serbest arama değil: saha çizgi
    # modeli 180° dönme altında kendine eşit olduğu için serbest arama 47 m
    # yanlış çapa üretmişti) ve %85 inlier istenir.
    allow_reacquire: bool = False
    # Kesmeyi kare kare tespit et ve kalibratöre bildir. Kesme bilinmezse
    # kalibratör kaymış homografiyle devam etmeyi dener ve yanlış çizgiye
    # kilitlenir.
    detect_cuts: bool = False
    # Ağır çekim tekrarları ayıkla. Yayında tekrar canlı akışın arasına girer;
    # canlı dakikayla kaydedilirse 68. dakikadaki atak 71'e yazılır ve aynı olay
    # iki kez sayılır. Farklı açıdan gelen tekrarlar zaten kalibrasyon kapılarınca
    # eleniyor; buradaki hedef ANA KAMERADAN gelen ağır çekim (sorunsuz kalibre
    # olur, o yüzden görünmez). `detect_cuts` ile aynı ölçümleri paylaşır.
    detect_replays: bool = False
    preview_path: str | None = None
    preview_width: int = 1600


@dataclass
class SampledObservation:
    order: int
    frame_idx: int
    seconds: float
    persons: list[tuple[int, float, float, float, float, float]]  # tid, x1,y1,x2,y2, conf
    ball: tuple[float, float, float] | None                        # cx, cy, conf
    ball_source: str | None = None                                 # det | roi | interp
    # Kare başına kalibrasyon açıkken bu karenin kendi homografisi; None ise
    # hattın sabit kalibrasyonu kullanılır (sabit kamera).
    calibration: PitchCalibration | None = None


def video_info(path: str | Path) -> dict[str, Any]:
    import cv2

    cap = cv2.VideoCapture(str(path))
    try:
        return {
            "fps": cap.get(cv2.CAP_PROP_FPS) or 25.0,
            "frames": int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
            "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        }
    finally:
        cap.release()


def iter_video_frames(path: str | Path, fps: float, max_seconds: float | None = None) -> Iterator[tuple[int, int, float, np.ndarray]]:
    """(order, frame_idx, seconds, frame_rgb) — kaynak fps'e göre atlayarak örnekler."""
    import cv2

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise FileNotFoundError(f"video açılamadı: {path}")
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    stride = max(1, round(src_fps / fps))
    idx = 0
    order = 0
    try:
        while True:
            ok, bgr = cap.read()
            if not ok:
                break
            if idx % stride == 0:
                seconds = idx / src_fps
                if max_seconds is not None and seconds > max_seconds:
                    break
                yield order, idx, seconds, cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                order += 1
            idx += 1
    finally:
        cap.release()


def _on_pitch_mask(det, calib: PitchCalibration | None, margin_m: float) -> np.ndarray:
    """Kutu alt-orta noktası saha (+marj) içinde mi — kalibrasyon yoksa hepsi True."""
    if calib is None or len(det) == 0:
        return np.ones(len(det), dtype=bool)
    return np.array([
        calib.is_on_pitch((x1 + x2) / 2, y2, margin_m=margin_m)
        for x1, _y1, x2, y2 in det.xyxy
    ], dtype=bool)


def _search_ball_roi(det: RFDetrDetector, rgb: np.ndarray, center: tuple[float, float], roi_w: int, threshold: float) -> tuple[float, float, float] | None:
    """Son bilinen top konumu çevresinde küçük pencerede (native çözünürlük) top ara."""
    h, w = rgb.shape[:2]
    roi_h = int(roi_w * 9 / 16)
    cx, cy = center
    x0 = int(min(max(cx - roi_w / 2, 0), max(w - roi_w, 0)))
    y0 = int(min(max(cy - roi_h / 2, 0), max(h - roi_h, 0)))
    crop = rgb[y0:y0 + roi_h, x0:x0 + roi_w]
    if crop.size == 0:
        return None
    d = det.predict_single(crop)
    balls = d[np.isin(d.class_id, list(det.ball_ids))]
    if len(balls) == 0:
        return None
    i = int(np.argmax(balls.confidence))
    if float(balls.confidence[i]) < threshold:
        return None
    bx1, by1, bx2, by2 = (float(v) for v in balls.xyxy[i])
    return (x0 + (bx1 + bx2) / 2, y0 + (by1 + by2) / 2, float(balls.confidence[i]))


def interpolate_ball(samples: list[SampledObservation], max_gap: int) -> int:
    """Ardışık iki top gözlemi arasındaki ≤ max_gap örneklik boşlukları doğrusal doldur."""
    filled = 0
    known = [i for i, s in enumerate(samples) if s.ball is not None]
    for a, b in zip(known, known[1:], strict=False):
        gap = b - a - 1
        if gap <= 0 or gap > max_gap:
            continue
        (ax, ay, _), (bx, by, _) = samples[a].ball, samples[b].ball  # type: ignore[misc]
        for k in range(1, gap + 1):
            t = k / (gap + 1)
            samples[a + k].ball = (ax + (bx - ax) * t, ay + (by - ay) * t, 0.0)
            samples[a + k].ball_source = "interp"
            filled += 1
    return filled


def collect_observations(
    video_path: str | Path,
    cfg: PipelineConfig,
    *,
    detector: RFDetrDetector | None = None,
    calib: PitchCalibration | None = None,
    progress: bool = True,
) -> tuple[list[SampledObservation], TeamAssigner, dict[str, Any]]:
    """Kalibrasyon verilirse saha dışı tespitler (yedek kulübesi, seyirci) takipten
    ÖNCE elenir: takım kümelemesi ve takip kimlikleri yalnız sahadakilerle kurulur.

    Üçüncü dönen değer kare başına kalibrasyonun **dürüstlük karnesi**: kaç kare
    kalibre oldu, kaç kare atıldı, kaç kesme görüldü. Yayın görüntüsünde bu oran
    çıktının ne kadarına güvenilebileceğini söyler ve özete yazılır."""
    import supervision as sv

    det = detector or RFDetrDetector(cfg.detector)
    tracker = sv.ByteTrack(
        track_activation_threshold=cfg.track_activation_threshold,
        lost_track_buffer=max(1, int(cfg.lost_track_seconds * cfg.track_fps)),
        minimum_matching_threshold=0.8,
        frame_rate=round(cfg.track_fps),
        minimum_consecutive_frames=1,
    )
    teams = TeamAssigner()
    per_frame = None
    if cfg.per_frame_calibration:
        if calib is None:
            raise ValueError("kare başına kalibrasyon için çapa kalibrasyon gerekir")
        from app.tracking.pitch_lines import PerFrameCalibrator

        per_frame = PerFrameCalibrator(
            calib, image_size=(int(calib.image_size[0]), int(calib.image_size[1])),
            allow_reacquire=cfg.allow_reacquire,
        )
    # Tekrar süzgeci kesme dedektörünün ölçümlerini kullanır (faz korelasyonu
    # ikinci kez hesaplanmasın), o yüzden ikisinden biri isteniyorsa dedektör kurulur.
    cut_detector = None
    if per_frame is not None and (cfg.detect_cuts or cfg.detect_replays):
        from app.tracking.camera import CutDetector

        cut_detector = CutDetector()
    replay_filter = None
    if cut_detector is not None and cfg.detect_replays:
        from app.tracking.replay import ReplayFilter

        replay_filter = ReplayFilter()
    cuts_seen = 0
    replays_seen = 0
    skipped_uncalibrated = 0
    samples: list[SampledObservation] = []
    hits: dict[int, int] = {}
    last_ball: tuple[float, float, int] | None = None   # cx, cy, order
    roi_max_age = max(1, int(cfg.ball_gap_seconds * cfg.track_fps))

    for order, frame_idx, seconds, rgb in iter_video_frames(video_path, cfg.track_fps, cfg.max_seconds):
        frame_calib = calib
        if per_frame is not None:
            import cv2

            bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            if cut_detector is not None:
                if cut_detector.update(bgr) == "cut" and cfg.detect_cuts:
                    # Süreklilik koptu. Kalibratöre söylemezsek kaymış homografiyle
                    # devam etmeyi dener ve yanlış çizgiye kilitlenebilir.
                    per_frame.mark_cut()
                    cuts_seen += 1
                if replay_filter is not None:
                    v = replay_filter.update(cut_detector.last_gray,
                                             cut_detector.last_motion)
                    if v.is_replay:
                        # Tekrar karesi: canlı dakikayla kaydedilirse zaman
                        # çizgisi kayar ve olay iki kez sayılır. Konum ÜRETİLMEZ.
                        replays_seen += 1
                        if progress and replays_seen % 25 == 1:
                            print(f"  kare {order} tekrar sayıldı — {v.reason}",
                                  flush=True)
                        continue
            fc = per_frame.process(bgr)
            if not fc.ok:
                # Kalibre edilemeyen kare: konum üretmek yerine atla. Takipçiye de
                # verilmez; kopuk kimlik, yanlış konumdan iyidir.
                skipped_uncalibrated += 1
                if progress and skipped_uncalibrated % 25 == 1:
                    print(f"  kare {order} atlandı — {fc.reason}", flush=True)
                continue
            frame_calib = fc.calibration
        all_det = det.detect(rgb)
        persons, balls = det.split(all_det)
        persons = persons[_on_pitch_mask(persons, frame_calib, cfg.pitch_margin_m)]
        balls = balls[_on_pitch_mask(balls, frame_calib, 1.0)]
        if len(balls) > 0:
            balls = balls[balls.confidence >= cfg.ball_threshold]
        tracked = tracker.update_with_detections(persons)
        rows: list[tuple[int, float, float, float, float, float]] = []
        for xyxy, conf, tid in zip(tracked.xyxy, tracked.confidence, tracked.tracker_id, strict=True):
            if tid is None:
                continue
            tid = int(tid)
            hits[tid] = hits.get(tid, 0) + 1
            x1, y1, x2, y2 = (float(v) for v in xyxy)
            rows.append((tid, x1, y1, x2, y2, float(conf)))
            teams.observe(tid, torso_color(rgb, (x1, y1, x2, y2)))

        ball = None
        ball_source = None
        if len(balls) > 0:
            i = int(np.argmax(balls.confidence))
            bx1, by1, bx2, by2 = (float(v) for v in balls.xyxy[i])
            ball = ((bx1 + bx2) / 2, (by1 + by2) / 2, float(balls.confidence[i]))
            ball_source = "det"
        elif last_ball is not None and order - last_ball[2] <= roi_max_age:
            found = _search_ball_roi(det, rgb, (last_ball[0], last_ball[1]), cfg.ball_roi_px, cfg.ball_threshold * 0.8)
            if found is not None and (frame_calib is None
                                      or frame_calib.is_on_pitch(found[0], found[1], margin_m=1.0)):
                ball, ball_source = found, "roi"
        if ball is not None:
            last_ball = (ball[0], ball[1], order)
        samples.append(SampledObservation(order, frame_idx, seconds, rows, ball, ball_source,
                                          calibration=frame_calib if per_frame else None))
        if progress and order % 50 == 0:
            print(f"  kare {order} · t={seconds:6.1f}s · oyuncu={len(rows)} · top={ball_source or '-'}", flush=True)

    # Kısa ömürlü (gürültü) takipleri at
    min_hits = max(1, round(cfg.min_track_seconds * cfg.track_fps))
    weak = {t for t, n in hits.items() if n < min_hits}
    for s in samples:
        s.persons = [r for r in s.persons if r[0] not in weak]
    interpolate_ball(samples, roi_max_age)
    if per_frame is not None and progress:
        print(f"  kare başına kalibrasyon: {per_frame.frames_calibrated} kare kalibre, "
              f"{per_frame.frames_rejected} atlandı (oran {per_frame.calibrated_ratio})",
              flush=True)
        if cfg.detect_cuts and cut_detector is not None:
            print(f"  kesme: {cuts_seen} (her kesmede çapadan yeniden yakalama "
                  f"{'AÇIK' if cfg.allow_reacquire else 'kapalı — takip kopar'})",
                  flush=True)
        if replay_filter is not None:
            uyari = "" if replay_filter.mask_found else (
                " (skorboard bindirmesi bulunamadı — tekrar süzgeci etkisiz, "
                "hiçbir kare atılmadı)")
            print(f"  tekrar: {replays_seen} kare atıldı{uyari}", flush=True)
    stats: dict[str, Any] = {"per_frame_calibration": per_frame is not None}
    if per_frame is not None:
        stats.update({
            "frames_calibrated": per_frame.frames_calibrated,
            "frames_rejected": per_frame.frames_rejected,
            "calibrated_ratio": per_frame.calibrated_ratio,
            "cuts": cuts_seen if cfg.detect_cuts else None,
            "allow_reacquire": cfg.allow_reacquire,
            "replays_dropped": replays_seen if replay_filter is not None else None,
            "overlay_mask_found": (replay_filter.mask_found
                                   if replay_filter is not None else None),
        })
    return samples, teams, stats


def output_stride(cfg: PipelineConfig) -> int:
    return max(1, round(cfg.track_fps / cfg.fps_out))


def compute_velocities(
    samples: list[SampledObservation],
    calib: PitchCalibration,
    track_fps: float,
) -> tuple[dict[int, dict[int, float]], dict[int, float]]:
    """Merkezi farkla hız (m/s): oyuncu → {order: {tid: v}}, top → {order: v}.

    Kenar örneklerde tek yönlü fark; uç değerler fiziksel sınırla kırpılır.
    """
    pos: list[dict[int, tuple[float, float]]] = []
    ball_pos: list[tuple[float, float] | None] = []
    for s in samples:
        # Kare başına kalibrasyonda her karenin kendi homografisi kullanılmalı;
        # aksi halde kameranın hareketi oyuncu hızı sanılır.
        c = s.calibration or calib
        pos.append({tid: c.image_to_pitch_m((x1 + x2) / 2, y2) for tid, x1, _y1, x2, y2, _c in s.persons})
        ball_pos.append(c.image_to_pitch_m(s.ball[0], s.ball[1]) if s.ball else None)

    def speed(a: tuple[float, float], b: tuple[float, float], dt: float) -> float:
        return float(np.hypot(b[0] - a[0], b[1] - a[1]) / dt) if dt > 0 else 0.0

    player_v: dict[int, dict[int, float]] = {}
    ball_v: dict[int, float] = {}
    n = len(samples)
    for i in range(n):
        out: dict[int, float] = {}
        # Kalibre edilemeyen kareler atlandığı için ardışık örnekler eşit aralıklı
        # olmayabilir; zaman farkı örnek indisinden değil GERÇEK saniyeden alınır.
        dt_prev = samples[i].seconds - samples[i - 1].seconds if i > 0 else 1.0 / track_fps
        dt_next = samples[i + 1].seconds - samples[i].seconds if i + 1 < n else 1.0 / track_fps
        for tid, p in pos[i].items():
            prev = pos[i - 1].get(tid) if i > 0 else None
            nxt = pos[i + 1].get(tid) if i + 1 < n else None
            if prev is not None and nxt is not None:
                v = speed(prev, nxt, dt_prev + dt_next)
            elif prev is not None:
                v = speed(prev, p, dt_prev)
            elif nxt is not None:
                v = speed(p, nxt, dt_next)
            else:
                continue
            out[tid] = round(min(v, MAX_PLAYER_SPEED_MPS), 2)
        player_v[samples[i].order] = out
        b = ball_pos[i]
        if b is not None:
            prev_b = ball_pos[i - 1] if i > 0 else None
            next_b = ball_pos[i + 1] if i + 1 < n else None
            if prev_b is not None and next_b is not None:
                bv = speed(prev_b, next_b, dt_prev + dt_next)
            elif prev_b is not None:
                bv = speed(prev_b, b, dt_prev)
            elif next_b is not None:
                bv = speed(b, next_b, dt_next)
            else:
                bv = None
            if bv is not None:
                ball_v[samples[i].order] = round(min(bv, MAX_BALL_SPEED_MPS), 2)
    return player_v, ball_v


def build_frames(
    samples: list[SampledObservation],
    team_by_track: dict[int, int | None],
    calib: PitchCalibration,
    *,
    match_id: int,
    home_team_id: int,
    away_team_id: int,
    cfg: PipelineConfig,
) -> list[TrackingFrame]:
    stride = output_stride(cfg)
    player_v, ball_v = compute_velocities(samples, calib, cfg.track_fps)
    out: list[TrackingFrame] = []
    for s in samples:
        if s.order % stride != 0:
            continue
        vmap = player_v.get(s.order, {})
        players = [
            TrackObservation(
                track_id=tid, u=(x1 + x2) / 2, v=y2,
                team=team_by_track.get(tid), conf=conf,
                velocity_mps=vmap.get(tid),
            )
            for tid, x1, y1, x2, y2, conf in s.persons
        ]
        ball = BallObservation(s.ball[0], s.ball[1], s.ball[2], velocity_mps=ball_v.get(s.order)) if s.ball else None
        fr = build_frame(
            match_id=match_id, seconds=s.seconds, order=s.order,
            calib=s.calibration or calib,
            players=players, ball=ball, home_team_id=home_team_id, away_team_id=away_team_id,
            period=cfg.period, clip_offset_minutes=cfg.clip_offset_minutes,
            ball_estimated=(s.ball_source == "interp"),
            source_name=cfg.source_name,
        )
        if fr is not None:
            out.append(fr)
    return out


def write_preview(
    video_path: str | Path,
    samples: list[SampledObservation],
    team_by_track: dict[int, int | None],
    calib: PitchCalibration,
    cfg: PipelineConfig,
    out_path: str | Path,
) -> None:
    """Etiketli önizleme (çıktı fps'inde): kutular (takım rengi), takip id, top, saha çizgileri."""
    import cv2

    by_frame_idx = {s.frame_idx: s for s in samples}
    # BGR: ev sahibi yeşil, deplasman kırmızı, atanmamış sarı
    colors = {0: (90, 200, 40), 1: (60, 80, 230), None: (60, 200, 200)}
    writer = None
    scale = 1.0
    for _order, frame_idx, _seconds, rgb in iter_video_frames(video_path, cfg.fps_out, cfg.max_seconds):
        s = by_frame_idx.get(frame_idx)
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        if writer is None:
            h, w = bgr.shape[:2]
            scale = min(1.0, cfg.preview_width / w)
            size = (int(w * scale), int(h * scale))
            writer = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"mp4v"), cfg.fps_out, size)
        _draw_pitch_lines(bgr, calib)
        if s is not None:
            for tid, x1, y1, x2, y2, _conf in s.persons:
                c = colors[team_by_track.get(tid)]
                cv2.rectangle(bgr, (int(x1), int(y1)), (int(x2), int(y2)), c, 2)
                cv2.putText(bgr, str(tid), (int(x1), int(y1) - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.6, c, 2)
            if s.ball:
                col = (255, 255, 255) if s.ball_source != "interp" else (200, 200, 200)
                cv2.circle(bgr, (int(s.ball[0]), int(s.ball[1])), 8, col, 2 if s.ball_source != "interp" else 1)
        if scale < 1.0:
            bgr = cv2.resize(bgr, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        writer.write(bgr)
    if writer is not None:
        writer.release()


def _draw_pitch_lines(bgr: np.ndarray, calib: PitchCalibration) -> None:
    """Saha dış hattı + orta çizgi + ceza sahalarını görüntüye geri-izdüşür (kalibrasyon kontrolü)."""
    import cv2

    Hinv = np.linalg.inv(calib.homography)
    L, W = calib.pitch_length_m, calib.pitch_width_m

    def px(x: float, y: float) -> tuple[int, int]:
        p = Hinv @ np.array([x, y, 1.0])
        return int(p[0] / p[2]), int(p[1] / p[2])

    polys = [
        [(0, 0), (L, 0), (L, W), (0, W)],
        [(L / 2, 0), (L / 2, W)],
        [(0, W / 2 - 20.16), (16.5, W / 2 - 20.16), (16.5, W / 2 + 20.16), (0, W / 2 + 20.16)],
        [(L, W / 2 - 20.16), (L - 16.5, W / 2 - 20.16), (L - 16.5, W / 2 + 20.16), (L, W / 2 + 20.16)],
    ]
    for poly in polys:
        pts = np.array([px(*p) for p in poly], dtype=np.int32)
        cv2.polylines(bgr, [pts], isClosed=len(poly) > 2, color=(255, 255, 255), thickness=2)


def process_video(
    video_path: str | Path,
    calib: PitchCalibration,
    *,
    match_id: int,
    home_team_id: int,
    away_team_id: int,
    cfg: PipelineConfig | None = None,
    detector: RFDetrDetector | None = None,
    team_anchor: np.ndarray | None = None,
) -> tuple[list[TrackingFrame], dict[str, Any]]:
    """`team_anchor` (2×3 forma rengi) verilirse takım kimliği küme büyüklüğü
    yerine bu renklere sabitlenir — canlı segment akışında takımların
    segmentler arası yer değiştirmemesi için (bkz. teams.TeamAssigner.fit)."""
    cfg = cfg or PipelineConfig()
    samples, assigner, calib_stats = collect_observations(
        video_path, cfg, detector=detector, calib=calib)
    assignment = assigner.fit(team_anchor)
    frames = build_frames(
        samples, assignment.team_by_track, calib,
        match_id=match_id, home_team_id=home_team_id, away_team_id=away_team_id, cfg=cfg,
    )
    if cfg.preview_path:
        write_preview(video_path, samples, assignment.team_by_track, calib, cfg, cfg.preview_path)
    tracks = {tid for s in samples for tid, *_ in s.persons}
    per_frame = [len(s.persons) for s in samples]
    summary = {
        "sampled_frames": len(samples),
        "track_fps": cfg.track_fps,
        "frames_written": len(frames),
        "fps_out": cfg.fps_out,
        "tracks": len(tracks),
        "players_per_frame_mean": round(float(np.mean(per_frame)), 1) if per_frame else 0.0,
        "team_counts": {
            "home": sum(1 for t in tracks if assignment.team_by_track.get(t) == 0),
            "away": sum(1 for t in tracks if assignment.team_by_track.get(t) == 1),
            "unassigned": sum(1 for t in tracks if assignment.team_by_track.get(t) is None),
        },
        "ball_frames": sum(1 for s in samples if s.ball),
        "ball_sources": {
            k: sum(1 for s in samples if s.ball_source == k) for k in ("det", "roi", "interp")
        },
        "calibration_reprojection_m": round(calib.reprojection_error_m, 3),
        # Yayın görüntüsünde çıktının ne kadarına güvenilebileceğini söyler:
        # kalibre olmayan kareler ATILDI, yani düşük oran "az veri" demektir,
        # "kötü veri" değil. Canlı hat bunu ekrana basar.
        "calibration_stats": calib_stats,
        # Canlı akışta bir sonraki segmente çapa olarak geçilir (takım kimliği
        # segmentler arası sabit kalsın diye) — bkz. scripts/track_live.py.
        "team_colors": [[round(float(c), 1) for c in row] for row in assignment.centers],
    }
    return frames, summary
