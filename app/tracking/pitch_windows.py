"""Sabit kamerada sahayı hiç görmeyen dilim pencerelerini atlayan ürün dedektörü (venv-cv).

Neden: panoramik sabit kamerada karenin bir bölümü gökyüzü, tribün ve saha kenarıdır. Dedektör
o pencereleri de işler; oradaki tespitleri ürün zaten saha çevresi süzgeciyle atar. 4096x1080
panoramada 4 dilim kare başına 55 pencere demektir ve bu, işlem süresinin neredeyse tamamıdır
(docs/measurements/panorama-speed-attribution-2026-11-13.json).

Dilim geometrisi DEĞİŞMEZ: pencereler dondurulmuş dedektörün ürettiğiyle aynıdır, yalnız bir
kısmı işlenmez. Bu yüzden tutulan pencerelerdeki tespitler aynı görüntü parçalarından gelir.

Neden ayrı modül: `detect.py` ve `pipeline.py` kör kontroller için hash'le dondurulmuş ölçüm
kodudur. Bu davranış onlara yazılamaz; ürün işçisi (`scripts/track_video_product.py`) çalışırken
`install()` ile bağlar. Ön kayıt: docs/measurements/pitch-window-skip-preregistration.json.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from app.tracking.calibration import PitchCalibration
from app.tracking.detect import DetectorConfig, RFDetrDetector

# Ön kayıtla dondurulmuş değerler; değiştirmek yeni ölçüm ister.
PITCH_MARGIN_M = 2.0
SIDE_PAD_RATIO = 0.15
# Ayağı pencerenin altında kalan oyuncunun gövdesi bu pencerededir: aşağıya bir pencere boyu bakılır.
BELOW_PAD_RATIO = 1.0
GRID_STEP_PX = 16


def pitch_grid(calibration: PitchCalibration, *, margin_m: float = PITCH_MARGIN_M,
               step: int = GRID_STEP_PX) -> tuple[np.ndarray, np.ndarray]:
    """Sahaya (payıyla) düşen görüntü noktaları: (u dizisi, v dizisi)."""
    width, height = calibration.image_size
    points = [(u, v) for v in range(0, height, step) for u in range(0, width, step)
              if calibration.is_on_pitch(float(u), float(v), margin_m=margin_m)]
    if not points:
        return np.empty(0), np.empty(0)
    us, vs = np.array(points, dtype=float).T
    return us, vs


def windows_seeing_pitch(offsets: np.ndarray, slice_wh: tuple[int, int],
                         pitch_points: tuple[np.ndarray, np.ndarray]) -> np.ndarray:
    """Her pencere için: kendisinde, yan payında ya da altındaki bir pencere boyunda saha var mı."""
    us, vs = pitch_points
    side, below = SIDE_PAD_RATIO * slice_wh[0], BELOW_PAD_RATIO * slice_wh[1]
    keep = np.zeros(len(offsets), dtype=bool)
    for index, (x1, y1, x2, y2) in enumerate(offsets):
        keep[index] = bool(((us >= x1 - side) & (us < x2 + side) & (vs >= y1) & (vs < y2 + below)).any())
    return keep


def balanced_batch(windows: int) -> int:
    """Tutulan pencereleri iki dengeli gruba böler (dondurulmuş dedektördeki kuralla aynı fikir)."""
    return max(1, (windows + 1) // 2)


class PitchWindowDetector(RFDetrDetector):
    """`RFDetrDetector` + saha dışı pencereleri atlama. Uygulanamadığı her durumda üst sınıfa döner."""

    _pitch_points: tuple[np.ndarray, np.ndarray]
    _calibration_size: tuple[int, int]
    _kept_offsets: np.ndarray | None
    windows_total: int
    windows_kept: int

    @classmethod
    def from_detector(cls, detector: RFDetrDetector, calibration: PitchCalibration) -> PitchWindowDetector:
        """Yüklenmiş dedektörü (model bellekte) devralır; model ikinci kez yüklenmez."""
        product = cls.__new__(cls)
        product.__dict__.update(detector.__dict__)
        product._pitch_points = pitch_grid(calibration)
        product._calibration_size = (int(calibration.image_size[0]), int(calibration.image_size[1]))
        product._kept_offsets = None
        product.windows_total = product.windows_kept = 0
        return product

    def _slice_plan(self, width: int, height: int) -> tuple[tuple[int, int], tuple[int, int]]:
        cols, rows = self.cfg.tile_grid(width, height)
        tile = (int(width / cols), int(height / rows))
        return tile, (int(tile[0] * self.cfg.tile_overlap), int(tile[1] * self.cfg.tile_overlap))

    def _applies(self, width: int, height: int) -> bool:
        return self.cfg.tiles > 1 and (width, height) == self._calibration_size and len(self._pitch_points[0]) > 0

    def _prepare(self, width: int, height: int) -> int:
        if not self._applies(width, height):
            return super()._prepare(width, height)
        if self._kept_offsets is None:
            import supervision as sv

            tile, overlap = self._slice_plan(width, height)
            offsets = sv.InferenceSlicer._generate_offset(resolution_wh=(width, height), slice_wh=tile,
                                                          overlap_wh=overlap)
            keep = windows_seeing_pitch(offsets, tile, self._pitch_points)
            self._kept_offsets = offsets[keep]
            self.windows_total, self.windows_kept = len(offsets), int(keep.sum())
            print(f"saha dışı pencereler atlanıyor: {self.windows_kept}/{self.windows_total} pencere işlenecek",
                  flush=True)
        batch = balanced_batch(len(self._kept_offsets))
        if not self._prepared:
            self._prepared = True
            if batch > 1 and self.cfg.half and self.device.startswith("cuda"):
                try:
                    self.model.inference(dtype=self._torch.float16, batch_size=batch)
                    self._fixed_batch = batch
                except Exception:  # noqa: BLE001 — fp16/derleme opsiyonel, üst sınıfla aynı davranış
                    self._fixed_batch = None
        return batch

    def detect(self, frame_rgb: np.ndarray) -> Any:
        height, width = frame_rgb.shape[:2]
        if not self._applies(width, height):
            return super().detect(frame_rgb)
        import supervision as sv

        batch = self._prepare(width, height)
        kept = self._kept_offsets
        if kept is None or len(kept) == 0:
            return super().detect(frame_rgb)
        tile, overlap = self._slice_plan(width, height)
        slicer = sv.InferenceSlicer(
            callback=self._predict_batch if batch > 1 else self._predict,
            slice_wh=tile, overlap_wh=overlap, iou_threshold=0.3, batch_size=batch,
        )
        # Dilimleyici pencereleri bu çağrıyla üretir; aynı pencerelerin yalnız sahayı görenleri verilir.
        slicer._generate_offset = lambda **_: kept
        det = slicer(frame_rgb)
        return det[np.isin(det.class_id, list(self.person_ids | self.ball_ids))]


def install(calibration: PitchCalibration) -> None:
    """Bu süreçte `pipeline`'ın kuracağı torch dedektörünü ürün sürümüyle değiştirir.

    Yalnız ürün işçisinin kendi sürecinde, kamera sabit ve kalibrasyon verilmişken çağrılır.
    ONNX dedektörü ve tek dilim olduğu gibi kalır.
    """
    from app.tracking import pipeline

    original = pipeline.make_detector

    def make_product_detector(cfg: DetectorConfig | None = None) -> Any:
        detector = original(cfg)
        if type(detector) is RFDetrDetector and detector.cfg.tiles > 1:
            return PitchWindowDetector.from_detector(detector, calibration)
        return detector

    setattr(pipeline, "make_detector", make_product_detector)  # noqa: B010 — mypy işlev adına atamayı reddeder
