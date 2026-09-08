"""Oyuncu + top tespiti — RF-DETR (Apache-2.0), COCO ön-eğitimli.

ultralytics/YOLO kullanılmaz (AGPL-3.0, ticari üründe lisans yükü).
torch/rfdetr yalnız burada, fonksiyon içinde import edilir (venv-cv).

Yüksek çözünürlüklü tam-saha/drone görüntülerinde oyuncular çok küçük kalır;
`tiles>1` ile görüntü parçalara bölünüp (supervision InferenceSlicer) tespit
edilir, kesişen kutular NMS ile birleşir.
"""

from __future__ import annotations

import contextlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

PERSON_NAMES = {"person"}
BALL_NAMES = {"sports ball"}


@dataclass
class DetectorConfig:
    model: str = "medium"       # nano | small | medium | large
    threshold: float = 0.35
    tiles: int = 1              # 1 = tam kare; 2 → 2×2, 3 → 3×3 dilim
    tile_overlap: float = 0.15
    resolution: int | None = None
    device: str | None = None   # None → cuda varsa cuda
    batch_size: int = 16        # dilimler toplu tahmin (GPU doluluğu)
    # İnce ayarlı ağırlık klasörü (scripts/train_topview_detector.py çıktısı:
    # checkpoint_best_total.pth + meta.json). None → COCO ön-eğitimli.
    weights: str | None = None


class RFDetrDetector:
    def __init__(self, cfg: DetectorConfig | None = None) -> None:
        import supervision as sv  # noqa: F401  (varlık kontrolü)
        import torch
        from rfdetr import RFDETRBase, RFDETRLarge, RFDETRMedium, RFDETRNano, RFDETRSmall

        self.cfg = cfg or DetectorConfig()
        meta = self._load_meta(self.cfg.weights)
        model_name = meta.get("model", self.cfg.model) if meta else self.cfg.model
        cls = {
            "nano": RFDETRNano, "small": RFDETRSmall, "medium": RFDETRMedium,
            "base": RFDETRBase, "large": RFDETRLarge,
        }[model_name]
        device = self.cfg.device or ("cuda" if torch.cuda.is_available() else "cpu")
        kwargs: dict[str, Any] = {"device": device}
        resolution = self.cfg.resolution or (meta.get("resolution") if meta else None)
        if resolution:
            kwargs["resolution"] = int(resolution)
        if meta:
            kwargs["pretrain_weights"] = str(Path(self.cfg.weights) / "checkpoint_best_total.pth")  # type: ignore[arg-type]
        self.model = cls(**kwargs)
        self._meta = meta
        # Derlenmiş model sabit batch ister; dilimli+batch modda son grup küçük
        # kalır → orada derleme atlanır (batch kazancı derleme kaybını karşılar).
        if not (self.cfg.tiles > 1 and self.cfg.batch_size > 1):
            with contextlib.suppress(Exception):  # optimize opsiyonel
                self.model.optimize_for_inference()
        self.device = device
        if meta:
            # İnce ayarlı model sınıfları 0-tabanlı indeksle döner (class_names sırası);
            # meta'daki COCO kategori id'leri (1..n) değil.
            names = getattr(self.model, "class_names", None)
            if isinstance(names, list | tuple) and names:
                self._class_names = {i: str(n) for i, n in enumerate(names)}
            else:
                self._class_names = {
                    i: str(v) for i, (_k, v) in enumerate(sorted(
                        meta.get("classes", {}).items(), key=lambda kv: int(kv[0]),
                    ))
                }
            self.person_ids = {i for i, n in self._class_names.items() if n == "player"}
            self.ball_ids = {i for i, n in self._class_names.items() if n == "ball"}
        else:
            self._class_names = self._resolve_class_names()
            self.person_ids = {i for i, n in self._class_names.items() if n in PERSON_NAMES}
            self.ball_ids = {i for i, n in self._class_names.items() if n in BALL_NAMES}

    @staticmethod
    def _load_meta(weights: str | None) -> dict[str, Any] | None:
        if not weights:
            return None
        path = Path(weights) / "meta.json"
        if not path.exists():
            raise FileNotFoundError(f"ince ayar meta.json yok: {path}")
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _resolve_class_names() -> dict[int, str]:
        from rfdetr.assets.coco_classes import COCO_CLASSES

        if isinstance(COCO_CLASSES, dict):
            return {int(k): str(v) for k, v in COCO_CLASSES.items()}
        return {i: str(n) for i, n in enumerate(COCO_CLASSES)}

    def _predict(self, image_rgb: np.ndarray):
        det = self.model.predict(image_rgb, threshold=self.cfg.threshold)
        # rfdetr her sonuca kaynak görüntüyü metadata olarak iliştirir; dilimler
        # birleştirilirken çakışır → temizle.
        det.metadata = {}
        return det

    def _predict_batch(self, images: list[np.ndarray]):
        """Dilimleri tek seferde GPU'ya ver (InferenceSlicer batch_size>1)."""
        out = self.model.predict(list(images), threshold=self.cfg.threshold)
        if not isinstance(out, list):
            out = [out]
        for d in out:
            d.metadata = {}
        return out

    def detect(self, frame_rgb: np.ndarray):
        """→ supervision.Detections (yalnız person + sports ball)."""
        import supervision as sv

        if self.cfg.tiles > 1:
            h, w = frame_rgb.shape[:2]
            tw, th = int(w / self.cfg.tiles), int(h / self.cfg.tiles)
            ov = self.cfg.tile_overlap
            # Küçük kutularda dilim sınırındaki çiftler düşük IoU verir → 0.3
            slicer = sv.InferenceSlicer(
                callback=self._predict_batch if self.cfg.batch_size > 1 else self._predict,
                slice_wh=(tw, th),
                overlap_wh=(int(tw * ov), int(th * ov)),
                iou_threshold=0.3,
                batch_size=self.cfg.batch_size,
            )
            det = slicer(frame_rgb)
        else:
            det = self._predict(frame_rgb)
        keep = np.isin(det.class_id, list(self.person_ids | self.ball_ids))
        return det[keep]

    def split(self, det) -> tuple[Any, Any]:
        """(persons, balls) olarak ayır."""
        persons = det[np.isin(det.class_id, list(self.person_ids))]
        balls = det[np.isin(det.class_id, list(self.ball_ids))]
        return persons, balls
