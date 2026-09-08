"""Video → TrackingFrame hattı (venv-cv işçisi).

Akış:
1. Videoyu `track_fps` hızında örnekle (cv2) — takip için yüksek (15 fps):
   küçük/hızlı oyuncularda ardışık kareler arası IoU eşleşmesi ancak böyle tutar
2. Her karede RF-DETR ile oyuncu/top tespiti (dilimli)
3. ByteTrack ile takip kimliği (supervision)
4. Forma rengi biriktir → klip sonunda takım kümeleme
5. `fps_out` hızında (5 fps) TrackingFrame üret — kalibrasyon homografisiyle
6. (opsiyonel) Etiketli önizleme videosu — görsel doğrulama için

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
    clip_offset_minutes: float = 0.0
    period: int = 1
    preview_path: str | None = None
    preview_width: int = 1600


@dataclass
class SampledObservation:
    order: int
    frame_idx: int
    seconds: float
    persons: list[tuple[int, float, float, float, float, float]]  # tid, x1,y1,x2,y2, conf
    ball: tuple[float, float, float] | None                        # cx, cy, conf


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


def collect_observations(
    video_path: str | Path,
    cfg: PipelineConfig,
    *,
    detector: RFDetrDetector | None = None,
    calib: PitchCalibration | None = None,
    progress: bool = True,
) -> tuple[list[SampledObservation], TeamAssigner]:
    """Kalibrasyon verilirse saha dışı tespitler (yedek kulübesi, seyirci) takipten
    ÖNCE elenir: takım kümelemesi ve takip kimlikleri yalnız sahadakilerle kurulur."""
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
    samples: list[SampledObservation] = []
    hits: dict[int, int] = {}

    for order, frame_idx, seconds, rgb in iter_video_frames(video_path, cfg.track_fps, cfg.max_seconds):
        all_det = det.detect(rgb)
        persons, balls = det.split(all_det)
        persons = persons[_on_pitch_mask(persons, calib, cfg.pitch_margin_m)]
        balls = balls[_on_pitch_mask(balls, calib, 1.0)]
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
        if len(balls) > 0:
            i = int(np.argmax(balls.confidence))
            bx1, by1, bx2, by2 = (float(v) for v in balls.xyxy[i])
            ball = ((bx1 + bx2) / 2, (by1 + by2) / 2, float(balls.confidence[i]))
        samples.append(SampledObservation(order, frame_idx, seconds, rows, ball))
        if progress and order % 50 == 0:
            print(f"  kare {order} · t={seconds:6.1f}s · oyuncu={len(rows)} · top={'✓' if ball else '-'}", flush=True)

    # Kısa ömürlü (gürültü) takipleri at
    min_hits = max(1, round(cfg.min_track_seconds * cfg.track_fps))
    weak = {t for t, n in hits.items() if n < min_hits}
    for s in samples:
        s.persons = [r for r in s.persons if r[0] not in weak]
    return samples, teams


def output_stride(cfg: PipelineConfig) -> int:
    return max(1, round(cfg.track_fps / cfg.fps_out))


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
    out: list[TrackingFrame] = []
    for s in samples:
        if s.order % stride != 0:
            continue
        players = [
            TrackObservation(
                track_id=tid, u=(x1 + x2) / 2, v=y2,
                team=team_by_track.get(tid), conf=conf,
            )
            for tid, x1, y1, x2, y2, conf in s.persons
        ]
        ball = BallObservation(s.ball[0], s.ball[1], s.ball[2]) if s.ball else None
        fr = build_frame(
            match_id=match_id, seconds=s.seconds, order=s.order, calib=calib,
            players=players, ball=ball, home_team_id=home_team_id, away_team_id=away_team_id,
            period=cfg.period, clip_offset_minutes=cfg.clip_offset_minutes,
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
    """Etiketli önizleme: kutular (takım rengi), takip id, top, saha çizgileri izdüşümü."""
    import cv2

    by_order = {s.order: s for s in samples}
    # BGR: ev sahibi yeşil, deplasman kırmızı, atanmamış sarı
    colors = {0: (90, 200, 40), 1: (60, 80, 230), None: (60, 200, 200)}
    writer = None
    scale = 1.0
    for order, _idx, _seconds, rgb in iter_video_frames(video_path, cfg.track_fps, cfg.max_seconds):
        s = by_order.get(order)
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        if writer is None:
            h, w = bgr.shape[:2]
            scale = min(1.0, cfg.preview_width / w)
            size = (int(w * scale), int(h * scale))
            writer = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"mp4v"), cfg.track_fps, size)
        _draw_pitch_lines(bgr, calib)
        if s is not None:
            for tid, x1, y1, x2, y2, _conf in s.persons:
                c = colors[team_by_track.get(tid)]
                cv2.rectangle(bgr, (int(x1), int(y1)), (int(x2), int(y2)), c, 2)
                cv2.putText(bgr, str(tid), (int(x1), int(y1) - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.6, c, 2)
            if s.ball:
                cv2.circle(bgr, (int(s.ball[0]), int(s.ball[1])), 8, (255, 255, 255), 2)
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
) -> tuple[list[TrackingFrame], dict[str, Any]]:
    cfg = cfg or PipelineConfig()
    samples, assigner = collect_observations(video_path, cfg, detector=detector, calib=calib)
    assignment = assigner.fit()
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
        "calibration_reprojection_m": round(calib.reprojection_error_m, 3),
    }
    return frames, summary
