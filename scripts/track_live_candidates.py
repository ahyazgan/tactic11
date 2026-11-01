"""`track_live` + top adayı kaydı: takip sonucu aynı, düşük güvenli toplar yan dosyada (venv-cv).

Takip hattı (`app.tracking.pipeline`, `scripts.track_live`) dondurulmuş: her karede
yalnız güveni eşiği (0,3) geçen en güvenli topu tutar. 117092'de dokunuş anlarının
%40'ında gerçek topun yakınında bir aday var ama çoğu 0,3'ün altında
(docs/TOP-TESPITI-OLAY-OLCUMU.md). Bu sarmalayıcı dosyalara dokunmadan:

- dedektörü `CANDIDATE_THRESHOLD` ile kurar, hatta yine üretim eşiğinin üstünü
  verir (`RecordingDetector`) — takip girdisi değişmez;
- her örneklenen karede eşik altı dahil bütün top adaylarını
  `<watch>/ball_candidates/<segment>.json` dosyasına yazar.

Ek GPU işi yok: adaylar takibin zaten yaptığı tespitten gelir. Argümanlar
`track_live` ile aynıdır.

    venv-cv\\Scripts\\python.exe -m scripts.track_live_candidates --watch ... (track_live argümanları)
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

import numpy as np

CANDIDATE_THRESHOLD = 0.1


class RecordingDetector:
    """Dedektör vekili: altta düşük eşik, dışarıya üretim eşiği; son tam kareyi saklar."""

    def __init__(self, inner: Any, threshold: float) -> None:
        self._inner = inner
        self.threshold = threshold
        self.last: Any = None

    def detect(self, frame_rgb: np.ndarray) -> Any:
        det = self._inner.detect(frame_rgb)
        self.last = det
        return det[det.confidence >= self.threshold]

    def predict_single(self, image_rgb: np.ndarray) -> Any:
        det = self._inner.predict_single(image_rgb)
        return det[det.confidence >= self.threshold]

    def last_balls(self) -> list[list[float]]:
        """Son `detect` çağrısındaki bütün top adayları: [cx, cy, güven, w, h]."""
        if self.last is None:
            return []
        balls = self.last[np.isin(self.last.class_id, list(self._inner.ball_ids))]
        return [[round((x1 + x2) / 2, 1), round((y1 + y2) / 2, 1), round(float(c), 4),
                 round(x2 - x1, 1), round(y2 - y1, 1)]
                for (x1, y1, x2, y2), c in zip(balls.xyxy.tolist(), balls.confidence, strict=True)]

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


def install(candidate_threshold: float = CANDIDATE_THRESHOLD) -> None:
    """`make_detector` ve `collect_observations`'ı kayıt yapan sürümlerle değiştir."""
    import app.tracking.detect as detect
    import app.tracking.pipeline as pipeline

    make_detector = detect.make_detector
    collect = pipeline.collect_observations

    def recording_make_detector(cfg: Any) -> RecordingDetector:
        inner = make_detector(dataclasses.replace(cfg, threshold=min(cfg.threshold, candidate_threshold)))
        return RecordingDetector(inner, cfg.threshold)

    def recording_collect(video_path: Any, cfg: Any, *args: Any, **kwargs: Any) -> Any:
        det = kwargs.get("detector")
        if not isinstance(det, RecordingDetector):
            return collect(video_path, cfg, *args, **kwargs)
        rows: list[dict[str, Any]] = []
        inner_hook = kwargs.get("observation_hook")

        def hook(rgb: np.ndarray, all_det: Any, sample: Any) -> None:
            rows.append({"order": sample.order, "frame_idx": sample.frame_idx,
                         "seconds": round(float(sample.seconds), 4), "balls": det.last_balls()})
            if inner_hook is not None:
                inner_hook(rgb, all_det, sample)

        kwargs["observation_hook"] = hook
        result = collect(video_path, cfg, *args, **kwargs)
        video = Path(video_path)
        out = video.parent / "ball_candidates" / f"{video.stem}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"video": video.name, "threshold": candidate_threshold,
                                   "production_threshold": det.threshold, "samples": rows}), encoding="utf-8")
        tmp.replace(out)
        return result

    detect.make_detector = recording_make_detector
    pipeline.collect_observations = recording_collect


def main() -> int:
    install()
    from scripts import track_live

    return track_live.main()


if __name__ == "__main__":
    raise SystemExit(main())
