"""Oyuncu + top tespiti — RF-DETR (Apache-2.0), COCO ön-eğitimli.

ultralytics/YOLO kullanılmaz (AGPL-3.0, ticari üründe lisans yükü).
torch/rfdetr yalnız burada, fonksiyon içinde import edilir (venv-cv).

Yüksek çözünürlüklü tam-saha/drone görüntülerinde oyuncular çok küçük kalır;
`tiles>1` ile görüntü parçalara bölünüp (supervision InferenceSlicer) tespit
edilir, kesişen kutular NMS ile birleşir.

## İki arka uç: torch ve ONNX Runtime

`RFDetrDetector` (torch) ve `OnnxDetector` (onnxruntime) aynı arayüzü verir:
`detect(frame_rgb) → sv.Detections`, `split(det) → (persons, balls)`. Hattın
geri kalanı hangisinin çalıştığını bilmez (`make_detector`).

ONNX arka ucu neden var — ölçüldü (2026-09-11): Windows Smart App Control
ikili dosyaları İMZAYA değil bulut İTİBARINA göre engelliyor; yeni çıkan
torch tekerlekleri (cu128, hepsi) engelli, GPU (RTX 5060, Blackwell) yalnız
cu128 ile çalışıyor → torch ile GPU yok. onnxruntime-gpu Microsoft imzalı ve
CUDA 13 çalışma zamanıyla `CUDAExecutionProvider` aynı makinede çalışıyor.
Model `scripts/export_detector_onnx.py` ile (CPU torch yeter) bir kez ONNX'e
aktarılır; çıkarım torch'suz döner. Ön/son-işleme rfdetr'in kendi ONNX
yardımcılarıyla aynı sözleşmedir (bilinear, antialias yok, ImageNet
normalizasyonu; per-class sigmoid; Q×C çiftlerinden top-k, sonra eşik).
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
ONNX_MODEL_DIR = Path("data/tracking/models/onnx")
ONNX_NUM_SELECT = 300           # PostProcess varsayılanı: eşikten önce alınan Q×C çifti


@dataclass
class DetectorConfig:
    model: str = "medium"       # nano | small | medium | large
    threshold: float = 0.35
    tiles: int = 1              # yükseklik ekseninde dilim sayısı (1 = tam kare)
    tile_overlap: float = 0.15
    # Dilim en/boy oranı: dilimler bu orana yakın tutulur, sütun sayısı görüntü
    # oranından hesaplanır. 16:9 kaynakta tiles×tiles ızgarasıyla aynı sonuç;
    # panoramik (örn. 6500×1000) kaynakta dilimler yassılaşmaz — model eğitim
    # oranına yakın girdi görür.
    tile_aspect: float = 16 / 9
    resolution: int | None = None
    device: str | None = None   # None → cuda varsa cuda
    # Dilimler toplu tahmin. None → (tiles+1)²/2+1: örtüşmeli ızgara (tiles+1)²
    # dilim üretir, iki eşit batch + en fazla 1 dolgu (ölçüm: 6 dilim → 25 en hızlı).
    batch_size: int | None = None
    half: bool = True           # fp16 çıkarım (CUDA'da); CPU'da yok sayılır

    def tile_grid(self, width: int, height: int) -> tuple[int, int]:
        """(sütun, satır) — satır = `tiles`, sütun görüntü oranından."""
        rows = max(1, self.tiles)
        cols = max(1, round(rows * (width / max(height, 1)) / self.tile_aspect))
        return cols, rows

    def effective_batch_size(self, width: int = 1920, height: int = 1080) -> int:
        if self.batch_size is not None:
            return max(1, self.batch_size)
        if self.tiles <= 1:
            return 1
        cols, rows = self.tile_grid(width, height)
        # Örtüşmeli ızgara ≈ (cols+1)(rows+1) dilim → iki eşit batch + ≤1 dolgu
        return (cols + 1) * (rows + 1) // 2 + 1
    # İnce ayarlı ağırlık klasörü (scripts/train_topview_detector.py çıktısı:
    # checkpoint_best_total.pth + meta.json). None → COCO ön-eğitimli.
    weights: str | None = None
    # Arka uç: "auto" → ONNX modeli varsa (ya da torch yüklenemiyorsa) ONNX,
    # yoksa torch. "torch" / "onnx" zorlar.
    backend: str = "auto"
    # ONNX model yolu; None → `default_onnx_path()`
    onnx_model: str | None = None

    def default_onnx_path(self) -> Path:
        """`scripts/export_detector_onnx.py`'nin yazdığı yerle aynı kural."""
        if self.weights:
            return ONNX_MODEL_DIR / f"{Path(self.weights).name}.onnx"
        res = f"_r{self.resolution}" if self.resolution else ""
        return ONNX_MODEL_DIR / f"rfdetr_{self.model}{res}.onnx"


def make_detector(cfg: DetectorConfig | None = None) -> RFDetrDetector | OnnxDetector:
    """Arka ucu seç: ONNX modeli hazırsa (ya da torch bu makinede yüklenemiyorsa) ONNX.

    torch'un yüklenememesi gerçek bir durumdur (Smart App Control yeni
    tekerlekleri engelliyor); o zaman anlaşılır bir hata verilir — sessizce
    CPU'ya ya da hiçbir şeye düşülmez.
    """
    cfg = cfg or DetectorConfig()
    if cfg.backend == "onnx":
        return OnnxDetector(cfg)
    if cfg.backend == "torch":
        return RFDetrDetector(cfg)
    if cfg.backend != "auto":
        raise ValueError(f"backend {cfg.backend!r}: auto | torch | onnx")
    onnx_path = Path(cfg.onnx_model) if cfg.onnx_model else cfg.default_onnx_path()
    if onnx_path.exists():
        return OnnxDetector(cfg)
    try:
        import torch  # noqa: F401
    except (ImportError, OSError) as e:
        raise RuntimeError(
            f"torch yüklenemedi ({type(e).__name__}) ve ONNX modeli yok ({onnx_path}). "
            f"Bir kez `scripts/export_detector_onnx.py` çalıştır ya da --backend torch"
        ) from e
    return RFDetrDetector(cfg)


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
        # Derlenmiş model sabit batch ister; dilim sayısı kare boyutuna bağlı
        # olduğu için derleme ilk `detect()` çağrısına ertelenir.
        self._fixed_batch: int | None = None
        self._prepared = False
        self._torch = torch
        if self.cfg.tiles <= 1:
            with contextlib.suppress(Exception):  # optimize opsiyonel
                self.model.optimize_for_inference()
            self._prepared = True
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

    def predict_single(self, image_rgb: np.ndarray):
        """Tek görüntü (dilimsiz) tahmin — ROI aramaları için."""
        return self._predict(image_rgb)

    def _predict(self, image_rgb: np.ndarray):
        if self._fixed_batch:
            # Derlenmiş model tek görüntü kabul etmez → dolgulu batch yolu
            return self._predict_batch([image_rgb])[0]
        det = self.model.predict(image_rgb, threshold=self.cfg.threshold)
        # rfdetr her sonuca kaynak görüntüyü metadata olarak iliştirir; dilimler
        # birleştirilirken çakışır → temizle.
        det.metadata = {}
        return det

    def _predict_batch(self, images: list[np.ndarray]):
        """Dilimleri tek seferde GPU'ya ver (InferenceSlicer batch_size>1)."""
        batch = list(images)
        n = len(batch)
        if self._fixed_batch and n < self._fixed_batch:
            batch = batch + [batch[-1]] * (self._fixed_batch - n)
        out = self.model.predict(batch, threshold=self.cfg.threshold)
        if not isinstance(out, list):
            out = [out]
        out = out[:n]
        for d in out:
            d.metadata = {}
        return out

    def _prepare(self, width: int, height: int) -> int:
        """İlk kareyi görünce batch boyutunu sabitle + fp16 derle."""
        batch = self.cfg.effective_batch_size(width, height)
        if not self._prepared:
            self._prepared = True
            if batch > 1 and self.cfg.half and self.device.startswith("cuda"):
                # Derlenmiş fp16 model sabit batch ister → dilim grupları
                # `_predict_batch`'te doldurulur, fazlası atılır.
                try:
                    self.model.inference(dtype=self._torch.float16, batch_size=batch)
                    self._fixed_batch = batch
                except Exception:  # noqa: BLE001 — fp16/derleme opsiyonel
                    self._fixed_batch = None
        return batch

    def detect(self, frame_rgb: np.ndarray):
        """→ supervision.Detections (yalnız person + sports ball)."""
        import supervision as sv

        if self.cfg.tiles > 1:
            h, w = frame_rgb.shape[:2]
            batch = self._prepare(w, h)
            cols, rows = self.cfg.tile_grid(w, h)
            tw, th = int(w / cols), int(h / rows)
            ov = self.cfg.tile_overlap
            # Küçük kutularda dilim sınırındaki çiftler düşük IoU verir → 0.3
            slicer = sv.InferenceSlicer(
                callback=self._predict_batch if batch > 1 else self._predict,
                slice_wh=(tw, th),
                overlap_wh=(int(tw * ov), int(th * ov)),
                iou_threshold=0.3,
                batch_size=batch,
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


# --- ONNX Runtime arka ucu (torch'suz) ------------------------------------- #

_IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def preprocess_rgb(images: list[np.ndarray], height: int, width: int) -> np.ndarray:
    """RGB uint8 kareler → (N, 3, H, W) float32; rfdetr `predict()` sözleşmesi.

    Bilinear, yarı-piksel merkezli, antialias YOK (cv2 INTER_LINEAR tam bu);
    ImageNet normalizasyonu. PIL resize kullanılmaz — küçültürken antialias
    uygular ve güven skorlarını kaydırır (rfdetr'in kendi notu).
    """
    import cv2

    out = np.empty((len(images), 3, height, width), dtype=np.float32)
    for i, img in enumerate(images):
        if img.shape[0] != height or img.shape[1] != width:
            img = cv2.resize(img, (width, height), interpolation=cv2.INTER_LINEAR)
        arr = img.astype(np.float32) / 255.0
        arr = (arr - _IMAGENET_MEAN) / _IMAGENET_STD
        out[i] = arr.transpose(2, 0, 1)
    return out


def select_topk(scores_all: np.ndarray, threshold: float,
                num_select: int = ONNX_NUM_SELECT) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(Q, C) sigmoid skorlarından top-k sorgu/sınıf çifti, sonra eşik.

    rfdetr `PostProcess._select_topk` ile aynı: Q×C düzleştirilir, en yüksek
    `num_select` çift alınır, ardından `> threshold`. Sorgu başına argmax
    DEĞİL — bir sorgu iki sınıfta da eşiği geçebilir. Sıra: skor azalan, eşit
    skorda küçük indeks önce (deterministik).
    """
    if scores_all.ndim != 2:
        raise ValueError(f"scores_all (Q, C) olmalı; {scores_all.shape}")
    flat = scores_all.reshape(-1)
    n = min(int(num_select), flat.size)
    if n <= 0:
        e = np.empty(0, dtype=np.int64)
        return flat[:0], e, e
    order = np.lexsort((np.arange(flat.size), -flat))[:n]
    keep = flat[order] > threshold
    order = order[keep]
    num_classes = scores_all.shape[1]
    return flat[order], (order % num_classes).astype(np.int64), (order // num_classes).astype(np.int64)


def decode_rfdetr_outputs(
    boxes_cwh: np.ndarray, logits: np.ndarray, *, width: int, height: int,
    threshold: float, background_last: bool, num_select: int = ONNX_NUM_SELECT,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Tek karenin `dets` (Q,4 normalize cxcywh) + `labels` (Q,C logit) → (xyxy px, skor, sınıf).

    `background_last`: ince ayarlı kontrol noktalarında son sütun arka plandır
    ve seçimden ÖNCE atılır; seyrek COCO kontrol noktasında son sütun gerçek
    bir sınıftır (90), atılmaz. Saf numpy — supervision gerekmez, test edilebilir.
    """
    scores_all = 1.0 / (1.0 + np.exp(-np.clip(logits.astype(np.float32), -88, 88)))
    class_ids = np.arange(scores_all.shape[1])
    if background_last and scores_all.shape[1] > 1:
        scores_all, class_ids = scores_all[:, :-1], class_ids[:-1]
    scores, cls, qidx = select_topk(scores_all, threshold, num_select)
    cx, cy, bw, bh = boxes_cwh[qidx].T
    xyxy = np.stack([cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2], axis=1)
    xyxy = xyxy * np.array([width, height, width, height], dtype=np.float32)
    # Kare sınırına kırp: dilimli çıkarımda kenardan taşan kutu, birleştiricinin
    # (InferenceSlicer) "dilim dışı koordinat" uyarısını tetikliyordu.
    xyxy = np.clip(xyxy, 0.0, np.array([width, height, width, height], dtype=np.float32))
    return xyxy.astype(np.float32), scores.astype(np.float32), class_ids[cls].astype(int)


class OnnxDetector:
    """RF-DETR ONNX modeliyle tespit — torch gerekmez, GPU onnxruntime-gpu ile.

    Sınıf eşlemesi torch arka ucuyla AYNI kaynaktan gelir (COCO adları ya da
    ince ayar `meta.json`) → hat iki arka uçta aynı id'leri görür.
    """

    def __init__(self, cfg: DetectorConfig | None = None) -> None:
        import onnxruntime as ort
        import supervision as sv  # noqa: F401  (varlık kontrolü)

        self.cfg = cfg or DetectorConfig()
        path = Path(self.cfg.onnx_model) if self.cfg.onnx_model else self.cfg.default_onnx_path()
        if not path.exists():
            raise FileNotFoundError(
                f"ONNX modeli yok: {path} — `scripts/export_detector_onnx.py` ile üret")
        self.model_path = path
        providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        if self.cfg.device == "cpu":
            providers = ["CPUExecutionProvider"]
        with contextlib.suppress(Exception):   # yalnız bazı ORT sürümlerinde var
            ort.preload_dlls()
        available = ort.get_available_providers()
        so = ort.SessionOptions()
        # ORT "Memcpy nodes added" uyarısını her oturumda basar; bilgi amaçlı
        # (CUDA grafiği kapalı kalır), hata değil — yalnız hatalar kalsın.
        so.log_severity_level = 3
        self.session = ort.InferenceSession(
            str(path), sess_options=so, providers=[p for p in providers if p in available])
        active = self.session.get_providers()[0]
        self.device = "cuda" if active == "CUDAExecutionProvider" else "cpu"
        inp = self.session.get_inputs()[0]
        self.input_name = inp.name
        # (N, 3, H, W); N dinamikse sembol/None gelir
        self.height, self.width = int(inp.shape[2]), int(inp.shape[3])
        self.dynamic_batch = not isinstance(inp.shape[0], int)
        names = [o.name for o in self.session.get_outputs()]
        self._boxes_idx = next((i for i, n in enumerate(names) if "dets" in n), 0)
        self._logits_idx = next((i for i, n in enumerate(names) if "labels" in n), 1)

        meta = RFDetrDetector._load_meta(self.cfg.weights)
        self._meta = meta
        if meta:
            # İnce ayar: 0-tabanlı sınıf sırası (torch arka ucuyla aynı), son sütun arka plan
            self._class_names = {
                i: str(v) for i, (_k, v) in enumerate(sorted(
                    meta.get("classes", {}).items(), key=lambda kv: int(kv[0])))}
            self.background_last = True
            self.person_ids = {i for i, n in self._class_names.items() if n == "player"}
            self.ball_ids = {i for i, n in self._class_names.items() if n == "ball"}
        else:
            self._class_names = RFDetrDetector._resolve_class_names()
            self.background_last = False        # seyrek COCO: son sütun sınıf 90
            self.person_ids = {i for i, n in self._class_names.items() if n in PERSON_NAMES}
            self.ball_ids = {i for i, n in self._class_names.items() if n in BALL_NAMES}

    def _run(self, images: list[np.ndarray]) -> list[Any]:
        import supervision as sv

        batch = preprocess_rgb(images, self.height, self.width)
        outs: list[Any] = []
        # Statik batch'li modelde tek tek; dinamikte hepsi birden
        chunks = [batch] if self.dynamic_batch else [batch[i:i + 1] for i in range(len(batch))]
        for chunk in chunks:
            raw = self.session.run(None, {self.input_name: chunk})
            boxes, logits = raw[self._boxes_idx], raw[self._logits_idx]
            for b in range(chunk.shape[0]):
                k = len(outs)
                h, w = images[k].shape[:2]
                xyxy, scores, cls = decode_rfdetr_outputs(
                    boxes[b], logits[b], width=w, height=h,
                    threshold=self.cfg.threshold, background_last=self.background_last)
                outs.append(sv.Detections(xyxy=xyxy, confidence=scores, class_id=cls))
        return outs

    def predict_single(self, image_rgb: np.ndarray):
        return self._run([image_rgb])[0]

    def detect(self, frame_rgb: np.ndarray):
        """→ supervision.Detections (yalnız person + sports ball) — torch yoluyla aynı."""
        import supervision as sv

        if self.cfg.tiles > 1:
            h, w = frame_rgb.shape[:2]
            cols, rows = self.cfg.tile_grid(w, h)
            tw, th = int(w / cols), int(h / rows)
            ov = self.cfg.tile_overlap
            batch = self.cfg.effective_batch_size(w, h) if self.dynamic_batch else 1
            slicer = sv.InferenceSlicer(
                callback=self._run if batch > 1 else self.predict_single,
                slice_wh=(tw, th), overlap_wh=(int(tw * ov), int(th * ov)),
                iou_threshold=0.3, batch_size=batch,
            )
            det = slicer(frame_rgb)
        else:
            det = self.predict_single(frame_rgb)
        keep = np.isin(det.class_id, list(self.person_ids | self.ball_ids))
        return det[keep]

    def split(self, det) -> tuple[Any, Any]:
        persons = det[np.isin(det.class_id, list(self.person_ids))]
        balls = det[np.isin(det.class_id, list(self.ball_ids))]
        return persons, balls
