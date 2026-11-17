"""İki geçişli yayın takibinin duruşlarını analiz hattına kalibratör olarak verir. Yalnız maç sonrası.

Hat (`pipeline.collect_observations`) dışarıdan kalibratör kabul eder; bu sınıf `PerFrameCalibrator`ın
hattın kullandığı yüzünü taşır. Duruşlar hat koşmadan önce `track_two_pass` ile bulunur, hat sırasında
görüntüye bakılmaz. Hat her kare için `process` çağırmalıdır: tekrar süzgeci kareyi kalibratöre sormadan
atladığı için bu kiple birlikte kapatılır (`PipelineConfig.detect_replays=False`).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from app.tracking.broadcast_two_pass import Frames, TwoPassTrack, track_two_pass
from app.tracking.pitch_lines import FrameCalibration, calibration_from_homography

NO_POSE = "iki geçişli yayın takibi bu karede duruş üretmedi"


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


def calibrate_broadcast(video: str | Path, track_fps: float, max_seconds: float | None = None) -> BroadcastPoseCalibrator:
    """Videoyu iki kez okuyup hat için kalibratör kurar. Takip eşikleri 15 fps'te ölçüldü."""
    from app.tracking.pipeline import effective_track_fps, video_info

    fps = effective_track_fps(video_info(video)["fps"], track_fps)
    return BroadcastPoseCalibrator(track_two_pass(lambda: pipeline_frames(video, track_fps, max_seconds), fps))
