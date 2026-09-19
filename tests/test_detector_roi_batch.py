"""ROI optimization preserves the main compiled model and has a bounded fallback."""
from types import SimpleNamespace

import numpy as np
import pytest

from app.tracking.detect import DetectorConfig, RFDetrDetector


class Model:
    fail = False

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.preparations = []
        self.predictions = []

    def inference(self, **kwargs):
        self.preparations.append(kwargs)
        if self.fail:
            raise RuntimeError("optional compilation unavailable")

    def predict(self, images, *, threshold):
        self.predictions.append((len(images), threshold))
        return [SimpleNamespace(metadata={"image": "temporary"}) for _ in images]


def detector(**config):
    config.setdefault("roi_single_batch", True)
    result = RFDetrDetector.__new__(RFDetrDetector)
    result.cfg = DetectorConfig(threshold=.37, **config)
    result._model_kwargs = {"device": "cuda", "pretrain_weights": "existing-checkpoint", "resolution": 512}
    result.model = Model(**result._model_kwargs)
    result._roi_model = None
    result._roi_attempted = False
    result._fixed_batch = 28
    result.device = "cuda"
    result._torch = SimpleNamespace(float16="fp16")
    return result


def test_roi_is_lazy_independent_and_compiled_once():
    obj = detector()
    image = np.zeros((180, 320, 3), dtype=np.uint8)
    assert obj._roi_model is None
    first, second = obj.predict_single(image), obj.predict_single(image)
    assert first.metadata == second.metadata == {}
    assert obj._roi_model is not obj.model
    assert obj._roi_model.kwargs == obj._model_kwargs
    assert obj._roi_model.preparations == [{"dtype": "fp16", "batch_size": 1}]
    assert obj._roi_model.predictions == [(1, .37), (1, .37)]
    assert obj.model.preparations == obj.model.predictions == []
    assert obj._fixed_batch == 28


@pytest.mark.parametrize("mode", ["disabled", "cpu", "full_precision", "uncompiled", "single"])
def test_unsupported_or_disabled_settings_use_original_prediction(mode):
    obj = detector(roi_single_batch=mode != "disabled", half=mode != "full_precision")
    if mode == "cpu":
        obj.device = "cpu"
    if mode in {"uncompiled", "single"}:
        obj._fixed_batch = None if mode == "uncompiled" else 1
    calls = []
    obj._predict = lambda image: calls.append(image) or "original"
    image = np.zeros((180, 320, 3), dtype=np.uint8)
    assert obj.predict_single(image) == "original"
    assert calls[0] is image
    assert not obj._roi_attempted


def test_failed_roi_preparation_falls_back_once_without_replacing_main(monkeypatch, caplog):
    obj = detector()
    original = obj.model
    monkeypatch.setattr(Model, "fail", True)
    image = np.zeros((180, 320, 3), dtype=np.uint8)
    assert obj.predict_single(image).metadata == {}
    assert obj.predict_single(image).metadata == {}
    assert obj.model is original and obj._roi_model is None and obj._roi_attempted
    assert obj._fixed_batch == 28
    assert obj.model.predictions == [(28, .37), (28, .37)]
    assert len(caplog.records) == 1


def test_roi_models_are_not_shared_between_detector_instances():
    first, second = detector(), detector()
    second._model_kwargs["pretrain_weights"] = "another-checkpoint"
    image = np.zeros((180, 320, 3), dtype=np.uint8)
    first.predict_single(image)
    second.predict_single(image)
    assert first._roi_model is not second._roi_model
    assert first._roi_model.kwargs["pretrain_weights"] == "existing-checkpoint"
    assert second._roi_model.kwargs["pretrain_weights"] == "another-checkpoint"


def test_roi_optimization_is_not_enabled_by_default():
    assert DetectorConfig().roi_single_batch is False
