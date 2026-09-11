"""RF-DETR dedektörünü ONNX'e aktar + torch ile PARİTE kontrolü (venv-cv).

## Neden

Bu makinede (ve Smart App Control açık her Windows 11'de) yeni çıkan torch
tekerlekleri Uygulama Denetimi tarafından engelleniyor; GPU (Blackwell) yalnız
o tekerleklerle çalışıyor → torch ile GPU yok. onnxruntime-gpu Microsoft
imzalı ve CUDA 13 ile çalışıyor. Model bir kez ONNX'e aktarılır, hat
`app.tracking.detect.OnnxDetector` ile torch'suz döner.

Dışa aktarım torch ister ama CPU yeter (torch 2.5.1+cpu geçiyor). Çıktı,
`DetectorConfig.default_onnx_path()` ile aynı yere yazılır; `--backend auto`
onu görünce ONNX'i seçer.

## Parite — iddia değil ölçüm

Aktarım sonrası aynı kare iki arka uçla da işlenir ve kutular karşılaştırılır.
Eşleşme oranı ve en büyük kutu farkı yazılır; fark büyükse çıkış kodu 1 —
sessizce farklı bir dedektör kullanılmaz.

    venv-cv\\Scripts\\python.exe -m scripts.export_detector_onnx \\
        --weights data/tracking/models/rfdetr_top_small \\
        --sample data/tracking/videos/teamtrack_D_20220220_1530.mp4
    venv-cv\\Scripts\\python.exe -m scripts.export_detector_onnx --model medium
"""
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

from app.tracking.detect import DetectorConfig, OnnxDetector, RFDetrDetector

PARITY_IOU = 0.9          # aynı nesne sayılmak için kutu örtüşmesi
PARITY_MIN_MATCH = 0.9    # torch kutularının bu payı ONNX'te de bulunmalı


def _ensure_onnxsim() -> None:
    """`onnxsim` yoksa sadeleştirme adımını GEÇ (grafiği aynen bırak).

    rfdetr aktarımı onnxsim'i zorunlu çağırır; oysa bu makinede onnxsim'in
    derlenmiş modülü Uygulama Denetimi tarafından engelli, eski sürümlerin de
    py3.12 tekerleği yok. Sadeleştirme bir hız optimizasyonudur, doğruluk
    şartı değil — doğruluğu aşağıdaki parite kontrolü ölçer. Yer tutucu
    `simplify` modeli olduğu gibi döndürür; graphsurgeon/polygraphy
    optimizasyonu (rfdetr `OnnxOptimizer`) yine çalışır.
    """
    import types

    try:
        import onnxsim  # noqa: F401
        return
    except ImportError:
        pass
    import onnx

    stub = types.ModuleType("onnxsim")
    stub.simplify = lambda path, **_kw: (onnx.load(path), True)  # type: ignore[attr-defined]
    sys.modules["onnxsim"] = stub
    print("onnxsim yüklenemedi → sadeleştirme atlandı (grafik aynen; parite kontrolü karar verir)")


def _sample_frame(path: str, at_seconds: float) -> np.ndarray:
    import cv2

    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise SystemExit(f"örnek video açılamadı: {path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(at_seconds * fps))
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise SystemExit(f"{at_seconds:.1f}. saniyede kare okunamadı")
    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)


def _iou_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    if len(a) == 0 or len(b) == 0:
        return np.zeros((len(a), len(b)))
    x1 = np.maximum(a[:, None, 0], b[None, :, 0])
    y1 = np.maximum(a[:, None, 1], b[None, :, 1])
    x2 = np.minimum(a[:, None, 2], b[None, :, 2])
    y2 = np.minimum(a[:, None, 3], b[None, :, 3])
    inter = np.clip(x2 - x1, 0, None) * np.clip(y2 - y1, 0, None)
    area = lambda r: (r[:, 2] - r[:, 0]) * (r[:, 3] - r[:, 1])  # noqa: E731
    return inter / (area(a)[:, None] + area(b)[None, :] - inter + 1e-9)


def parity(torch_det, onnx_det, frame: np.ndarray) -> dict:
    """Aynı karede iki arka uç: eşleşen kutu payı, sınıf uyumu, skor farkı.

    Süreler ısınma SONRASI ölçülür: ilk CUDA çağrısı cuDNN ayarını da içerir ve
    gerçek kare maliyetini temsil etmez.
    """
    torch_det.detect(frame)
    onnx_det.detect(frame)
    t0 = time.time()
    a = torch_det.detect(frame)
    t_torch = time.time() - t0
    t0 = time.time()
    b = onnx_det.detect(frame)
    t_onnx = time.time() - t0
    iou = _iou_matrix(a.xyxy, b.xyxy)
    matched = 0
    score_gap = 0.0
    class_ok = 0
    for i in range(len(a)):
        if iou.shape[1] == 0:
            break
        j = int(iou[i].argmax())
        if iou[i, j] >= PARITY_IOU:
            matched += 1
            score_gap = max(score_gap, abs(float(a.confidence[i]) - float(b.confidence[j])))
            class_ok += int(a.class_id[i] == b.class_id[j])
    return {
        "torch_boxes": int(len(a)), "onnx_boxes": int(len(b)), "matched": matched,
        "match_ratio": round(matched / len(a), 3) if len(a) else 1.0,
        "class_agree": round(class_ok / matched, 3) if matched else 1.0,
        "max_score_gap": round(score_gap, 3),
        "torch_ms": round(t_torch * 1000), "onnx_ms": round(t_onnx * 1000),
        "onnx_device": onnx_det.device,
    }


def main() -> int:
    p = argparse.ArgumentParser(description="RF-DETR → ONNX + parite kontrolü")
    p.add_argument("--model", default="medium", choices=["nano", "small", "medium", "base", "large"])
    p.add_argument("--weights", default=None, help="İnce ayarlı ağırlık klasörü (meta.json + checkpoint)")
    p.add_argument("--resolution", type=int, default=None)
    p.add_argument("--out", default=None, help="ONNX yolu (varsayılan: DetectorConfig.default_onnx_path)")
    p.add_argument("--sample", default=None, help="Parite için örnek video")
    p.add_argument("--at-seconds", type=float, default=2.0)
    p.add_argument("--threshold", type=float, default=0.3)
    p.add_argument("--tiles", type=int, default=1)
    p.add_argument("--skip-parity", action="store_true")
    p.add_argument("--parity-only", action="store_true",
                   help="Var olan ONNX'i yeniden üretme, yalnız pariteyi ölç")
    args = p.parse_args()

    cfg = DetectorConfig(model=args.model, weights=args.weights, resolution=args.resolution,
                         threshold=args.threshold, tiles=args.tiles, backend="torch")
    out = Path(args.out) if args.out else cfg.default_onnx_path()
    out.parent.mkdir(parents=True, exist_ok=True)

    _ensure_onnxsim()
    t0 = time.time()
    det = RFDetrDetector(cfg)          # CPU yeter; export torch ister
    print(f"torch modeli yüklendi ({time.time() - t0:.1f}s, cihaz {det.device})")
    if args.parity_only:
        if not out.exists():
            print(f"ONNX yok: {out}")
            return 1
        print(f"var olan ONNX kullanılıyor: {out}")
    else:
        _export(det, out)

    if args.skip_parity:
        return 0
    sample = args.sample or "data/tracking/videos/teamtrack_D_20220220_1530.mp4"
    if not Path(sample).exists():
        print(f"parite atlandı: örnek video yok ({sample}) — --sample ver")
        return 0
    frame = _sample_frame(sample, args.at_seconds)
    onnx_cfg = DetectorConfig(model=args.model, weights=args.weights, resolution=args.resolution,
                              threshold=args.threshold, tiles=args.tiles, backend="onnx",
                              onnx_model=str(out))
    rep = parity(det, OnnxDetector(onnx_cfg), frame)
    print("\n=== PARİTE (aynı kare, torch vs ONNX) ===")
    for k, v in rep.items():
        print(f"  {k}: {v}")
    if rep["torch_boxes"] == 0:
        print("  sonuç: ÖLÇÜLEMEDİ — torch bu karede hiç kutu bulmadı; --tiles / --at-seconds değiştir")
        return 1
    ok = rep["match_ratio"] >= PARITY_MIN_MATCH and rep["class_agree"] >= PARITY_MIN_MATCH
    print("  sonuç:", "UYUMLU" if ok else "UYUMSUZ — ONNX modeli kullanılmamalı")
    return 0 if ok else 1


def _export(det: RFDetrDetector, out: Path) -> None:
    print("ONNX aktarımı…")
    with tempfile.TemporaryDirectory() as tmp:
        # rfdetr dosya adını kendi koyar; sonra bizim kurala taşınır. Dinamik
        # batch: dilimler tek seferde verilebilsin.
        produced = det.model.export(output_dir=tmp, dynamic_batch=True, verbose=False,
                                    output_name=out.stem)
        produced = Path(produced)
        if produced.is_dir():
            cands = sorted(produced.glob("*.onnx"))
            if not cands:
                raise SystemExit(f"aktarım dosya üretmedi: {produced}")
            produced = cands[0]
        shutil.copyfile(produced, out)
    print(f"yazıldı: {out} ({out.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    sys.exit(main())
