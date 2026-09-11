"""ONNX dedektör arka ucu — torch'suz ön/son-işleme sözleşmesi.

rfdetr `PostProcess` ile aynı kurallar: per-class sigmoid, Q×C çiftlerinden
top-k SONRA eşik (sorgu başına argmax değil), normalize cxcywh → piksel xyxy,
ince ayarlı modelde son sütun arka plan. Bunlar torch arka ucuyla aynı
kutuları üretmenin şartı; parite `scripts/export_detector_onnx.py` ile
gerçek modelde ölçülür, burada kurallar kilitlenir.

onnxruntime/cv2/supervision gerekmez: `decode_rfdetr_outputs` ve `select_topk`
saf numpy — ana venv'de ve CI'da koşar.
"""
from __future__ import annotations

import numpy as np
import pytest

from app.tracking.detect import DetectorConfig, decode_rfdetr_outputs, select_topk


def _logit(p: float) -> float:
    return float(np.log(p / (1.0 - p)))


def test_topk_lets_one_query_carry_two_classes() -> None:
    """Bir sorgu iki sınıfta da eşiği geçebilir — argmax bunu sessizce düşürürdü."""
    scores = np.array([[0.9, 0.8], [0.1, 0.2]])
    s, cls, q = select_topk(scores, threshold=0.5)
    assert q.tolist() == [0, 0] and cls.tolist() == [0, 1]
    assert s.tolist() == [0.9, 0.8]


def test_topk_caps_before_threshold_and_is_deterministic() -> None:
    scores = np.full((4, 2), 0.7)
    s, cls, q = select_topk(scores, threshold=0.5, num_select=3)
    assert len(s) == 3
    # eşit skorda küçük düz indeks önce: (q0,c0), (q0,c1), (q1,c0)
    assert q.tolist() == [0, 0, 1] and cls.tolist() == [0, 1, 0]


def test_topk_rejects_bad_shapes() -> None:
    with pytest.raises(ValueError):
        select_topk(np.zeros(5), 0.5)


def test_decode_maps_normalised_boxes_to_pixels_and_drops_background() -> None:
    """İnce ayarlı model: sütunlar [player, ball, arka plan]; arka plan seçilmez."""
    boxes = np.array([[0.5, 0.5, 0.2, 0.4], [0.25, 0.75, 0.1, 0.1]], dtype=np.float32)
    logits = np.array([
        [_logit(0.9), _logit(0.05), _logit(0.99)],   # oyuncu; arka plan yüksek ama atılır
        [_logit(0.1), _logit(0.8), _logit(0.2)],     # top
    ], dtype=np.float32)
    xyxy, scores, cls = decode_rfdetr_outputs(boxes, logits, width=1000, height=500,
                                              threshold=0.5, background_last=True)
    assert cls.tolist() == [0, 1]
    assert np.allclose(xyxy[0], [400, 150, 600, 350], atol=1e-3)
    assert np.allclose(xyxy[1], [200, 350, 300, 400], atol=1e-3)
    assert scores[0] == pytest.approx(0.9, abs=1e-4)


def test_decode_keeps_last_column_for_sparse_coco() -> None:
    """COCO kontrol noktasında son sütun gerçek sınıftır (90) — atılmaz."""
    boxes = np.array([[0.5, 0.5, 0.2, 0.2]], dtype=np.float32)
    logits = np.full((1, 91), _logit(0.01), dtype=np.float32)
    logits[0, 90] = _logit(0.8)
    _xyxy, _scores, cls = decode_rfdetr_outputs(boxes, logits, width=100, height=100,
                                                threshold=0.5, background_last=False)
    assert cls.tolist() == [90]


def test_decode_clips_boxes_to_the_frame() -> None:
    """Kenardan taşan kutu kare sınırına kırpılır (dilim birleştirici bunu ister)."""
    boxes = np.array([[0.95, 0.5, 0.3, 0.2]], dtype=np.float32)   # sağdan taşar
    logits = np.array([[_logit(0.9), _logit(0.01)]], dtype=np.float32)
    xyxy, _s, _c = decode_rfdetr_outputs(boxes, logits, width=100, height=50,
                                         threshold=0.5, background_last=True)
    assert xyxy[0].tolist() == pytest.approx([80.0, 20.0, 100.0, 30.0], abs=1e-3)


def test_decode_empty_when_nothing_clears_threshold() -> None:
    boxes = np.zeros((3, 4), dtype=np.float32)
    logits = np.full((3, 5), _logit(0.1), dtype=np.float32)
    xyxy, scores, cls = decode_rfdetr_outputs(boxes, logits, width=10, height=10,
                                              threshold=0.5, background_last=True)
    assert len(xyxy) == 0 and len(scores) == 0 and len(cls) == 0
    assert xyxy.shape == (0, 4)


def test_auto_backend_prefers_cuda_torch_then_onnx(monkeypatch, tmp_path) -> None:
    """Ölçüldü: dilimli çıkarımda torch fp16 ONNX'ten 3-4 kat hızlı → CUDA varsa torch.

    CUDA yoksa ONNX modeli varsa ONNX (SAC'lı / GPU'suz makine yedeği).
    """
    from app.tracking import detect as detect_mod

    built: list[str] = []
    monkeypatch.setattr(detect_mod, "RFDetrDetector", lambda cfg: built.append("torch"))
    monkeypatch.setattr(detect_mod, "OnnxDetector", lambda cfg: built.append("onnx"))
    onnx_file = tmp_path / "m.onnx"
    onnx_file.write_bytes(b"\x00")
    cfg = detect_mod.DetectorConfig(onnx_model=str(onnx_file))

    monkeypatch.setattr(detect_mod, "torch_cuda_available", lambda: True)
    detect_mod.make_detector(cfg)
    monkeypatch.setattr(detect_mod, "torch_cuda_available", lambda: False)
    detect_mod.make_detector(cfg)
    assert built == ["torch", "onnx"]

    # Zorlamalar seçiciyi atlar
    detect_mod.make_detector(detect_mod.DetectorConfig(backend="onnx"))
    detect_mod.make_detector(detect_mod.DetectorConfig(backend="torch"))
    assert built[2:] == ["onnx", "torch"]
    with pytest.raises(ValueError):
        detect_mod.make_detector(detect_mod.DetectorConfig(backend="tpu"))


def test_default_onnx_path_follows_weights_or_model() -> None:
    assert DetectorConfig(weights="data/tracking/models/rfdetr_top_small").default_onnx_path().name \
        == "rfdetr_top_small.onnx"
    assert DetectorConfig(model="medium").default_onnx_path().name == "rfdetr_medium.onnx"
    assert DetectorConfig(model="small", resolution=512).default_onnx_path().name \
        == "rfdetr_small_r512.onnx"


def test_preprocess_matches_imagenet_contract() -> None:
    cv2 = pytest.importorskip("cv2")  # noqa: F841 — yalnız varlık
    from app.tracking.detect import preprocess_rgb

    img = np.full((8, 8, 3), 255, dtype=np.uint8)
    out = preprocess_rgb([img], 8, 8)
    assert out.shape == (1, 3, 8, 8) and out.dtype == np.float32
    # (1 - mean) / std, kanal 0
    assert out[0, 0, 0, 0] == pytest.approx((1.0 - 0.485) / 0.229, abs=1e-4)
