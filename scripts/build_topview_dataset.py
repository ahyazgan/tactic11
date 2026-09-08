"""TeamTrack (drone/tepeden bakış) klipleri → RF-DETR ince ayar veri seti (COCO, dilimli).

Her klipten `--every` karede bir örnek alınır; 4K kare `--tile-w × --tile-h`
dilimlere bölünür (inference'taki dilimlemeyle aynı ölçek). İçinde en az bir
nesne merkezi olan dilimler + küçük oranda boş dilim yazılır. Sınıflar:
1=player (takım 0/1), 2=ball. Hakem etiketsiz → arka plan.

Kullanım (venv-cv):
    python -m scripts.build_topview_dataset --clips-dir <dir> --list <split name ...> \
        --out data/tracking/datasets/teamtrack_top --every 30 --tiles 6

`--list` satır biçimi: "<split> <clip_name> ..." (split ∈ train|val); val → valid+test.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

CATEGORIES = [
    {"id": 0, "name": "objects", "supercategory": "none"},
    {"id": 1, "name": "player", "supercategory": "objects"},
    {"id": 2, "name": "ball", "supercategory": "objects"},
]


def read_gt(csv_path: Path) -> dict[int, list[tuple[int, float, float, float, float]]]:
    """frame → [(cls, x, y, w, h)] — cls 1 oyuncu, 2 top."""
    with open(csv_path, encoding="utf-8") as f:
        rows = list(csv.reader(f))
    team, attr = rows[0], rows[2]
    pid = rows[1]
    out: dict[int, list[tuple[int, float, float, float, float]]] = {}
    for r in rows[4:]:
        if not r or not r[0]:
            continue
        fi = int(float(r[0]))
        ents: dict[tuple[str, str], dict[str, float]] = defaultdict(dict)
        for j in range(1, len(attr)):
            if r[j] != "":
                ents[(team[j], pid[j])][attr[j]] = float(r[j])
        boxes = []
        for (t, _p), a in ents.items():
            if not {"bb_left", "bb_top", "bb_width", "bb_height"} <= set(a):
                continue
            if a["bb_width"] <= 1 or a["bb_height"] <= 1:
                continue
            cls = 2 if t == "BALL" else 1
            boxes.append((cls, a["bb_left"], a["bb_top"], a["bb_width"], a["bb_height"]))
        out[fi] = boxes
    return out


def main() -> int:
    import cv2

    p = argparse.ArgumentParser()
    p.add_argument("--clips-dir", required=True)
    p.add_argument("--list", required=True, help="satır: <split> <clip_name> ...")
    p.add_argument("--out", required=True)
    p.add_argument("--every", type=int, default=30)
    p.add_argument("--tiles", type=int, default=6)
    p.add_argument("--empty-ratio", type=float, default=0.05)
    p.add_argument("--seed", type=int, default=0)
    args = p.parse_args()
    rng = random.Random(args.seed)

    with open(args.list, encoding="utf-8") as f:
        clips = [ln.split() for ln in f if ln.strip()]
    out = Path(args.out)
    coco = {s: {"images": [], "annotations": [], "categories": CATEGORIES} for s in ("train", "valid", "test")}
    img_id = {s: 0 for s in coco}
    ann_id = {s: 0 for s in coco}
    stats: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for split, name, *_ in clips:
        targets = ["train"] if split == "train" else ["valid", "test"]
        video = Path(args.clips_dir) / f"{name}.mp4"
        gt = read_gt(Path(args.clips_dir) / f"{name}.csv")
        cap = cv2.VideoCapture(str(video))
        fi = 0
        while True:
            ok, bgr = cap.read()
            if not ok:
                break
            # TeamTrack CSV kare numaraları 1-tabanlı; video indeksi 0-tabanlı
            gt_key = fi + 1
            if fi % args.every == 0 and gt_key in gt:
                h, w = bgr.shape[:2]
                tw, th = w // args.tiles, h // args.tiles
                for ty in range(args.tiles):
                    for tx in range(args.tiles):
                        x0, y0 = tx * tw, ty * th
                        boxes = []
                        for cls, bx, by, bw, bh in gt[gt_key]:
                            cx, cy = bx + bw / 2, by + bh / 2
                            if not (x0 <= cx < x0 + tw and y0 <= cy < y0 + th):
                                continue
                            nx1, ny1 = max(bx - x0, 0), max(by - y0, 0)
                            nx2, ny2 = min(bx + bw - x0, tw), min(by + bh - y0, th)
                            if nx2 - nx1 < 2 or ny2 - ny1 < 2:
                                continue
                            boxes.append((cls, nx1, ny1, nx2 - nx1, ny2 - ny1))
                        if not boxes and rng.random() > args.empty_ratio:
                            continue
                        tile = bgr[y0:y0 + th, x0:x0 + tw]
                        fname = f"{name}_f{fi:05d}_t{ty}{tx}.jpg"
                        for s in targets:
                            d = out / s
                            d.mkdir(parents=True, exist_ok=True)
                            cv2.imwrite(str(d / fname), tile, [cv2.IMWRITE_JPEG_QUALITY, 92])
                            iid = img_id[s]
                            img_id[s] += 1
                            coco[s]["images"].append({"id": iid, "file_name": fname, "width": tw, "height": th})
                            for cls, bx, by, bw, bh in boxes:
                                coco[s]["annotations"].append({
                                    "id": ann_id[s], "image_id": iid, "category_id": cls,
                                    "bbox": [round(bx, 1), round(by, 1), round(bw, 1), round(bh, 1)],
                                    "area": round(bw * bh, 1), "iscrowd": 0, "segmentation": [],
                                })
                                ann_id[s] += 1
                                stats[s]["ball" if cls == 2 else "player"] += 1
                            stats[s]["tiles"] += 1
                            stats[s]["empty" if not boxes else "nonempty"] += 1
            fi += 1
        cap.release()
        print(f"{split} {name}: ok", flush=True)

    for s, c in coco.items():
        d = out / s
        d.mkdir(parents=True, exist_ok=True)
        with open(d / "_annotations.coco.json", "w", encoding="utf-8") as f:
            json.dump(c, f)
        print(f"{s}: {dict(stats[s])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
