"""RF-DETR ince ayarı — tepeden bakış (drone/panoramik) oyuncu + top (venv-cv, GPU).

Girdi: scripts/build_topview_dataset.py çıktısı (COCO; train/valid/test).
Çıktı: <out>/checkpoint_best_total.pth (+ meta.json: model boyutu, çözünürlük,
sınıf eşlemesi). Dedektör bu klasörü `--weights` ile alır.

Kullanım:
    venv-cv\\Scripts\\python.exe -m scripts.train_topview_detector \\
        --dataset data/tracking/datasets/teamtrack_top \\
        --out data/tracking/models/rfdetr_top_small --model small --epochs 8
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--model", default="small", choices=["nano", "small", "medium", "base", "large"])
    p.add_argument("--epochs", type=int, default=8)
    p.add_argument("--batch-size", type=int, default=8)
    p.add_argument("--grad-accum", type=int, default=2)
    p.add_argument("--lr", type=float, default=1e-4)
    p.add_argument("--resolution", type=int, default=None)
    p.add_argument("--workers", type=int, default=2)
    args = p.parse_args()

    from rfdetr import RFDETRBase, RFDETRLarge, RFDETRMedium, RFDETRNano, RFDETRSmall

    cls = {"nano": RFDETRNano, "small": RFDETRSmall, "medium": RFDETRMedium, "base": RFDETRBase, "large": RFDETRLarge}[args.model]
    kwargs = {}
    if args.resolution:
        kwargs["resolution"] = args.resolution
    model = cls(**kwargs)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    with open(Path(args.dataset) / "train" / "_annotations.coco.json", encoding="utf-8") as f:
        cats = json.load(f)["categories"]
    classes = {int(c["id"]): c["name"] for c in cats if c["name"] != "objects"}
    started = time.time()
    model.train(
        dataset_dir=args.dataset,
        epochs=args.epochs,
        batch_size=args.batch_size,
        grad_accum_steps=args.grad_accum,
        lr=args.lr,
        output_dir=str(out),
        num_workers=args.workers,
        tensorboard=False,
        wandb=False,
        early_stopping=False,
        checkpoint_interval=100,
    )
    resolution = getattr(getattr(model, "model_config", None), "resolution", args.resolution)
    meta = {
        "model": args.model,
        "resolution": resolution,
        "classes": classes,
        "person_class_ids": [i for i, n in classes.items() if n == "player"],
        "ball_class_ids": [i for i, n in classes.items() if n == "ball"],
        "dataset": args.dataset,
        "epochs": args.epochs,
        "elapsed_minutes": round((time.time() - started) / 60, 1),
    }
    with open(out / "meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print("\n=== Train done ===")
    for k, v in meta.items():
        print(f"  {k}: {v}")
    print("  checkpoints:", sorted(p.name for p in out.glob("*.pth")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
