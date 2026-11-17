"""İki geçişli yayın takibinin duruşlarını analiz hattına kalibratör olarak verir. Yalnız maç sonrası.

Hat (`pipeline.collect_observations`) dışarıdan kalibratör kabul eder; bu sınıf `PerFrameCalibrator`ın
hattın kullandığı yüzünü taşır. Duruşlar hat koşmadan önce `track_two_pass` ile bulunur, hat sırasında
görüntüye bakılmaz. Hat her kare için `process` çağırmalıdır: hattın tekrar süzgeci kareyi kalibratöre
sormadan atladığı için bu kiple birlikte kapatılır (`PipelineConfig.detect_replays=False`). Tekrarlar
iki geçişte süzülür: tekrar karesinde duruş yoktur, hat o kareyi kalibre edilememiş sayıp atlar.

`scripts/track_video.py` hash'le dondurulmuş ölçüm kodudur; kip oraya yazılmaz. Ürün işçisi
(`scripts/track_video_product.py --broadcast-two-pass`) `two_pass_process_video` ile bağlar.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np

from app.tracking.broadcast_two_pass import Frames, TwoPassTrack, frame_windows, track_two_pass
from app.tracking.pitch_lines import FrameCalibration, calibration_from_homography

NO_POSE = "iki geçişli yayın takibi bu karede duruş üretmedi"
FLAG = "--broadcast-two-pass"
EXIT_NO_CAMERA = 2


class BroadcastPoseCalibrator:
    """Kare sırasına göre hazır duruşu döner; duruş yoksa kare atlanır."""

    def __init__(self, track: TwoPassTrack) -> None:
        self.track = track
        self.frames_calibrated = 0
        self.frames_rejected = 0
        self.anchor_attempts = sum(track.anchor_sources.values())
        self.anchors_found = self.anchor_attempts - track.anchor_sources.get("rejected", 0)
        self.reanchors = 0
        self._order = 0

    @property
    def calibrated_ratio(self) -> float:
        seen = self.frames_calibrated + self.frames_rejected
        return round(self.frames_calibrated / seen, 3) if seen else 0.0

    def mark_cut(self) -> None:
        """Kesme iki geçişte ele alındı; hat yalnız kendi takipçisini sıfırlar."""

    def process(self, bgr: np.ndarray) -> FrameCalibration:
        pose = self.track.poses.get(self._order)
        self._order += 1
        if pose is None:
            self.frames_rejected += 1
            return FrameCalibration(None, None, NO_POSE)
        self.frames_calibrated += 1
        return FrameCalibration(calibration_from_homography(pose, self.track.size), None)


def pipeline_frames(video: str | Path, track_fps: float, max_seconds: float | None) -> Frames:
    """Hattın okuduğu karelerin aynısı: (hat sıra no, BGR)."""
    import cv2

    from app.tracking.pipeline import iter_video_frames

    for order, _index, _seconds, rgb in iter_video_frames(video, track_fps, max_seconds):
        yield order, cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def replay_windows(replays: set[int], fps: float) -> list[list[float]]:
    """Tekrar sayılan ardışık kareleri [başlangıç, bitiş] saniye aralıklarına toplar (denetim için)."""
    return [[round(a / fps, 1), round((b + 1) / fps, 1)] for a, b in frame_windows(replays)]


def calibrate_broadcast(video: str | Path, track_fps: float,
                        max_seconds: float | None = None) -> tuple[BroadcastPoseCalibrator, float]:
    """Videoyu iki kez okuyup hat için kalibratörü ve etkin takip hızını döner. Eşikler 15 fps'te ölçüldü."""
    from app.tracking.pipeline import effective_track_fps, video_info

    fps = effective_track_fps(video_info(video)["fps"], track_fps)
    return BroadcastPoseCalibrator(track_two_pass(lambda: pipeline_frames(video, track_fps, max_seconds), fps)), fps


def two_pass_process_video(process_video: Callable[..., Any]) -> Callable[..., Any]:
    """`pipeline.process_video`ı sarar: duruşları önce bulur, hatta kalibratör olarak verir.

    Kamera bulunamazsa ya da hat kare başına kalibrasyonla kurulmadıysa (`--camera broadcast` yok)
    çıktı üretmeden `EXIT_NO_CAMERA` ile çıkar.
    """

    def run(video_path: str | Path, calib: Any, *, cfg: Any, **kwargs: Any) -> Any:
        if not cfg.per_frame_calibration:
            print("HATA: iki geçişli yayın takibi yalnız yayın kamerasında çalışır (--camera broadcast)")
            raise SystemExit(EXIT_NO_CAMERA)
        print("iki geçişli yayın takibi: video iki kez okunuyor (hat bundan sonra başlar)", flush=True)
        calibrator, fps = calibrate_broadcast(video_path, cfg.track_fps, cfg.max_seconds)
        track = calibrator.track
        if track.camera is None:
            print("HATA: kamera konumu bulunamadı (ilk geçişte yeterli duruş yok) — duruş üretilmez")
            raise SystemExit(EXIT_NO_CAMERA)
        print(f"  kamera {track.camera.round(1).tolist()} m · duruşlu kare {len(track.poses)} · "
              f"bekçinin attığı {track.guard_rejected} · tekrar diye atılan {track.replay_rejected}", flush=True)
        frames, summary = process_video(video_path, calib, cfg=replace(cfg, detect_replays=False),
                                        calibrator=calibrator, **kwargs)
        summary["broadcast_two_pass"] = {
            "camera_m": track.camera.round(2).tolist(), "anchor_sources": track.anchor_sources,
            "guard_rejected": track.guard_rejected,
            "replay_filter": "kırmızı logo geçişi (J.League yayını); kapanışı görülmeyen pencere süzülmez",
            "replay_frames": len(track.replays), "replay_rejected": track.replay_rejected,
            "replay_windows_s": replay_windows(track.replays, fps),
            "replay_unclosed_windows_s": replay_windows(track.unclosed_replays, fps),
        }
        return frames, summary

    return run
