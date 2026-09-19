"""Fixed-camera Deep OC-SORT adapter with pinned OSNet appearance features.

This is an explicitly selected experimental backend. The validated default is
Supervision ByteTrack. No model download or silent backend fallback occurs here.
"""
from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np

MODEL_SHA256 = "2f38acc25e28cb29407635db2be315edc08d5457a904b72a9a11e427f41f3242"
DEFAULT_MODEL = "data/tracking/models/osnet_ain_ms_d_c.pth.tar"
PROFILE = "deepocsort-osnet-fixed-v1"


def verified_model_path(path: str) -> Path:
    model = Path(path).resolve()
    if not model.is_file():
        raise ValueError(f"OSNet model missing: {model}; see docs/TAKIP-REID-ENTEGRASYONU.md")
    with model.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
    if actual != MODEL_SHA256:
        raise ValueError("OSNet model SHA-256 does not match the pinned profile")
    return model


@lru_cache(maxsize=1)
def _load_model(path: str, device: str) -> Any:
    import torch
    from numpy._core.multiarray import scalar

    from app.tracking._vendor.deepocsort.osnet_ain import osnet_ain_x1_0

    model_path = verified_model_path(path)
    # Old training checkpoints include numpy scalar metrics. Allow only those
    # types, keep weights_only=True, and never deserialize an unverified file.
    safe = [(scalar, "numpy.core.multiarray.scalar"), np.dtype,
            type(np.dtype("float32")), type(np.dtype("float64"))]
    with torch.serialization.safe_globals(safe):
        checkpoint = torch.load(model_path, map_location="cpu", weights_only=True)
    model = osnet_ain_x1_0(num_classes=2510, pretrained=False)
    model.load_state_dict({k.removeprefix("module."): v for k, v in checkpoint["state_dict"].items()},
                          strict=True)
    return model.eval().to(device)


class OSNetEmbedder:
    """Whole-body preprocessing from upstream's general-model/grid_off path."""

    def __init__(self, path: str, *, device: str = "cuda"):
        import torch

        if device == "cuda" and not torch.cuda.is_available():
            raise ValueError("Deep OC-SORT requires CUDA for this production profile")
        self.path = str(verified_model_path(path))
        self.device = device
        self.model = _load_model(self.path, device)

    def compute_embedding(self, img: np.ndarray, bbox: np.ndarray, tag: str = "") -> np.ndarray:
        import cv2
        import torch

        if len(bbox) == 0:
            return np.empty((0, 512), dtype=np.float32)
        h, w = img.shape[:2]
        boxes = np.round(bbox).astype(np.int32)
        boxes[:, [0, 2]] = boxes[:, [0, 2]].clip(0, w)
        boxes[:, [1, 3]] = boxes[:, [1, 3]].clip(0, h)
        crops = []
        for x1, y1, x2, y2 in boxes:
            if x2 <= x1 or y2 <= y1:
                raise ValueError("Empty OSNet crop after clipping to source image")
            crop = cv2.cvtColor(img[y1:y2, x1:x2], cv2.COLOR_BGR2RGB)
            crop = cv2.resize(crop, (128, 256), interpolation=cv2.INTER_LINEAR).astype(np.float32)
            crop /= 255
            crop -= np.array((.485, .456, .406))
            crop /= np.array((.229, .224, .225))
            crops.append(crop.transpose(2, 0, 1))
        outputs = []
        with torch.inference_mode():
            for start in range(0, len(crops), 64):
                batch = torch.from_numpy(np.stack(crops[start:start + 64])).to(self.device)
                output = torch.nn.functional.normalize(self.model(batch), dim=-1)
                outputs.append(output.cpu().numpy())
        result = np.concatenate(outputs)
        if not np.isfinite(result).all() or np.any(np.linalg.norm(result, axis=1) < .99):
            raise ValueError("OSNet returned invalid appearance vectors")
        return result


class DeepOCSortTracker:
    """Return only original detection rows; isolate IDs and appearance per stream."""

    def __init__(self, *, threshold: float, lost_frames: int, embedder: Any = None,
                 appearance: bool = True):
        if not np.isfinite(threshold) or not 0 < threshold < 1:
            raise ValueError("Deep OC-SORT threshold must be between 0 and 1")
        if lost_frames < 0 or int(lost_frames) != lost_frames:
            raise ValueError("Deep OC-SORT lost_frames must be a nonnegative integer")
        if appearance and embedder is None:
            raise ValueError("Deep OC-SORT requires an appearance model")
        self.threshold = threshold
        self.max_time_lost = int(lost_frames)
        self.embedder = embedder
        self.appearance = appearance
        self.reset()

    def reset(self) -> None:
        from app.tracking._vendor.deepocsort.ocsort import OCSort

        self.tracker = OCSort(
            det_thresh=self.threshold, max_age=self.max_time_lost, min_hits=1,
            iou_threshold=.3, delta_t=3, inertia=.2, w_association_emb=.75,
            alpha_fixed_emb=.95, aw_param=.5, embedding_off=not self.appearance,
            cmc_off=True, aw_off=not self.appearance, new_kf_off=True, grid_off=True,
            embedder=self.embedder,
        )

    def update_with_detections(self, detections: Any, bgr: np.ndarray) -> Any:
        boxes = detections.xyxy
        confidence = detections.confidence
        if confidence is None or not np.isfinite(boxes).all() or not np.isfinite(confidence).all():
            raise ValueError("Tracker requires finite source boxes and confidences")
        if np.any(boxes[:, 2:] <= boxes[:, :2]) or np.any((confidence < 0) | (confidence > 1)):
            raise ValueError("Tracker requires positive boxes and confidence in [0, 1]")
        if bgr.ndim != 3 or bgr.shape[2] != 3 or bgr.dtype != np.uint8:
            raise ValueError("Tracker requires the source uint8 BGR image")
        # Upstream only reads img_tensor.shape to undo detector resizing. Our
        # RF-DETR boxes are already in source pixels, so scale is exactly 1.
        shape = SimpleNamespace(shape=(1, 3, *bgr.shape[:2]))
        rows = np.column_stack((boxes, confidence)).astype(float)
        output = self.tracker.update(rows, shape, bgr, tag="")
        indices = output[:, 5].astype(int)
        ids = output[:, 4].astype(int)
        if (not np.isfinite(output).all() or len(set(indices)) != len(indices)
                or len(set(ids)) != len(ids) or np.any(ids <= 0)
                or np.any(indices < 0) or np.any(indices >= len(detections))
                or not np.array_equal(output[:, 5], indices)
                or not np.array_equal(output[:, 4], ids)):
            raise ValueError("Tracker returned invalid source indices or identities")
        if np.any(confidence[indices] <= self.threshold):
            raise ValueError("Tracker returned an ineligible source detection")
        # Explicit source indices are propagated through both assignment rounds
        # in the vendored algorithm. No nearest-box rematching or guessed box.
        result = detections[indices]
        result.tracker_id = ids
        return result
