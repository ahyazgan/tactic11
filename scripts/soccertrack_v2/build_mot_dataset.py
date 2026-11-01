"""SoccerTrack Challenge MOT klipleri → RF-DETR ince ayar veri seti (COCO, dilimli).

Klipler 4096×1080, 25 fps, her karede 22 oyuncu kutusu (MOT: frame,id,x,y,w,h,…;
kareler 0-tabanlı). Her klipten `--every` karede bir örnek alınır ve kare
`--tiles` satırlık ızgaraya bölünür (çıkarımdaki `DetectorConfig.tile_grid` ile
aynı sütun kuralı). Merkezi dilimde olan kutular yazılır; boş dilimlerin
`--empty-ratio` kadarı tutulur. Sınıf 1 = oyuncu.

MOT etiketlerinde top YOK. Bu kliplerin dilimlerinde görünen top etiketsiz
kalacağından, modelin top tespitini unutmaması için `--base-dataset` (top
etiketli, ör. `data/tracking/datasets/teamtrack_mixed`) aynı bölünmelerle
kopyalanır.

    venv-cv\\Scripts\\python.exe -X utf8 -m scripts.soccertrack_v2.build_mot_dataset \\
        --clips-dir data/tracking/datasets/soccertrack_mot \\
        --train 117093 118575 118576 118577 --valid 128058 \\
        --base-dataset data/tracking/datasets/teamtrack_mixed \\
        --tiles 2 --every 50 --out data/tracking/datasets/soccertrack_mot_ft
"""
from __future__ import annotations

import argparse
import json
import random
import shutil
from collections import Counter, defaultdict
from pathlib import Path

CATEGORIES = [
    {"id": 0, "name": "objects", "supercategory": "none"},
    {"id": 1, "name": "player", "supercategory": "objects"},
    {"id": 2, "name": "ball", "supercategory": "objects"},
]


def read_mot(path: Path) -> dict[int, list[tuple[float, float, float, float]]]:
    boxes: dict[int, list[tuple[float, float, float, float]]] = defaultdict(list)
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.strip().split(",")
        if len(parts) < 6:
            continue
        frame, _tid, x, y, w, h = (float(v) for v in parts[:6])
        if w > 1 and h > 1:
            boxes[int(frame)].append((x, y, w, h))
    return boxes


def tile_boxes(boxes: list[tuple[float, float, float, float]], x0: int, y0: int, tw: int, th: int,
               ) -> list[tuple[float, float, float, float]]:
    """Merkezi dilimde olan kutular, dilim koordinatına kırpılmış."""
    out = []
    for bx, by, bw, bh in boxes:
        cx, cy = bx + bw / 2, by + bh / 2
        if not (x0 <= cx < x0 + tw and y0 <= cy < y0 + th):
            continue
        nx1, ny1 = max(bx - x0, 0.0), max(by - y0, 0.0)
        nx2, ny2 = min(bx + bw - x0, float(tw)), min(by + bh - y0, float(th))
        if nx2 - nx1 >= 2 and ny2 - ny1 >= 2:
            out.append((nx1, ny1, nx2 - nx1, ny2 - ny1))
    return out


def grid(width: int, height: int, tiles: int, aspect: float) -> tuple[int, int]:
    rows = max(1, tiles)
    return max(1, round(rows * (width / max(height, 1)) / aspect)), rows


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--clips-dir", type=Path, required=True)
    p.add_argument("--train", nargs="+", required=True)
    p.add_argument("--valid", nargs="+", required=True)
    p.add_argument("--base-dataset", type=Path, default=None)
    p.add_argument("--tiles", type=int, required=True)
    p.add_argument("--tile-aspect", type=float, default=16 / 9)
    p.add_argument("--every", type=int, default=50)
    p.add_argument("--empty-ratio", type=float, default=0.05)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()

    import cv2

    args.out.mkdir(parents=True, exist_ok=False)
    rng = random.Random(args.seed)
    coco = {s: {"images": [], "annotations": [], "categories": CATEGORIES} for s in ("train", "valid", "test")}
    stats: dict[str, Counter[str]] = {s: Counter() for s in coco}

    def add(split: str, src_or_img, fname: str, w: int, h: int, boxes: list[tuple[int, list[float]]]) -> None:
        d = args.out / split
        d.mkdir(parents=True, exist_ok=True)
        if isinstance(src_or_img, Path):
            shutil.copyfile(src_or_img, d / fname)
        else:
            cv2.imwrite(str(d / fname), src_or_img, [cv2.IMWRITE_JPEG_QUALITY, 92])
        iid = len(coco[split]["images"])
        coco[split]["images"].append({"id": iid, "file_name": fname, "width": w, "height": h})
        for cat, (bx, by, bw, bh) in boxes:
            coco[split]["annotations"].append({
                "id": len(coco[split]["annotations"]), "image_id": iid, "category_id": cat,
                "bbox": [round(bx, 1), round(by, 1), round(bw, 1), round(bh, 1)],
                "area": round(bw * bh, 1), "iscrowd": 0, "segmentation": []})
            stats[split]["ball" if cat == 2 else "player"] += 1
        stats[split]["images"] += 1

    # doğrulama klipleri hem valid hem test'e (RF-DETR üçünü de bekler)
    for split, names in (("train", args.train), ("valid", args.valid)):
        targets = ["train"] if split == "train" else ["valid", "test"]
        for name in names:
            gt = read_mot(args.clips_dir / f"{name}.txt")
            cap = cv2.VideoCapture(str(args.clips_dir / f"{name}.mp4"))
            fi = 0
            while True:
                ok, bgr = cap.read()
                if not ok:
                    break
                if fi % args.every == 0 and fi in gt:
                    h, w = bgr.shape[:2]
                    cols, rows = grid(w, h, args.tiles, args.tile_aspect)
                    tw, th = w // cols, h // rows
                    for ty in range(rows):
                        for tx in range(cols):
                            boxes = tile_boxes(gt[fi], tx * tw, ty * th, tw, th)
                            if not boxes and rng.random() > args.empty_ratio:
                                continue
                            tile = bgr[ty * th:(ty + 1) * th, tx * tw:(tx + 1) * tw]
                            for s in targets:
                                add(s, tile, f"st{name}_f{fi:05d}_t{ty}{tx}.jpg", tw, th,
                                    [(1, list(b)) for b in boxes])
                fi += 1
            cap.release()
            print(f"{split} {name}: {fi} kare", flush=True)

    if args.base_dataset is not None:
        for split in ("train", "valid", "test"):
            ann = json.loads((args.base_dataset / split / "_annotations.coco.json").read_text(encoding="utf-8"))
            by_image = defaultdict(list)
            for a in ann["annotations"]:
                by_image[a["image_id"]].append((int(a["category_id"]), [float(v) for v in a["bbox"]]))
            for img in ann["images"]:
                add(split, args.base_dataset / split / img["file_name"], f"base_{img['file_name']}",
                    int(img["width"]), int(img["height"]),
                    [(c, b) for c, b in by_image[img["id"]] if c in (1, 2)])
            print(f"base {split}: {len(ann['images'])} görüntü", flush=True)

    for split, c in coco.items():
        (args.out / split).mkdir(parents=True, exist_ok=True)
        (args.out / split / "_annotations.coco.json").write_text(json.dumps(c), encoding="utf-8")
        print(split, dict(stats[split]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
