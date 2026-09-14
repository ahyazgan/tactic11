"""Prepare blinded shirt-colour review at fixed times, independent of predictions/GT.

Run with venv-cv. Label manifest entries as blue, white, other, or uncertain
after looking at the numbered source crops. Those kit names are dataset-specific.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path


def select_samples(payload: dict, times: list[float]) -> list[dict]:
    selected = {}
    for seconds in times:
        sample = min(payload["samples"], key=lambda s: (round(abs(s["seconds"] - seconds), 8), s["seconds"]))
        selected[sample["frame_idx"]] = sample
    rows = []
    for sample in selected.values():
        for person in sample["persons"]:
            rows.append({"id": f"{payload['segment']}-{sample['frame_idx']}-{person[0]}",
                         "segment": payload["segment"], "frame_idx": sample["frame_idx"],
                         "seconds": sample["seconds"], "track": person[0], "bbox": person[1:5],
                         "video": payload["video"], "kit": None})
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--segments", type=int, nargs="+", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("choose a new output directory")
    import cv2
    from PIL import Image, ImageDraw

    args.out.mkdir(parents=True)
    records, hashes = [], {}
    for segment in args.segments:
        path = args.cache / f"seg_{segment:04d}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = select_samples(payload, [5.0, 20.0])
        if not rows:
            continue
        hashes[path.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
        hashes[payload["video"]] = hashlib.sha256(Path(payload["video"]).read_bytes()).hexdigest()
        sheet = Image.new("RGB", (1600, math.ceil(len(rows) / 8) * 210), "#111827")
        draw = ImageDraw.Draw(sheet)
        cap = cv2.VideoCapture(payload["video"])
        frames = {}
        for frame_idx in {r["frame_idx"] for r in rows}:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ok, frame = cap.read()
            if not ok:
                raise ValueError(f"cannot read frame {frame_idx} from {payload['video']}")
            frames[frame_idx] = frame
        cap.release()
        for i, row in enumerate(rows):
            x1, y1, x2, y2 = [round(v) for v in row["bbox"]]
            left, top = max(0, x1 - 12), max(0, y1 - 10)
            crop = frames[row["frame_idx"]][top:y2 + 10, left:x2 + 12]
            picture = Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
            ImageDraw.Draw(picture).rectangle((x1 - left, y1 - top, x2 - left, y2 - top), outline="#fbbf24")
            scale = min(190 / picture.width, 170 / picture.height)
            picture = picture.resize((round(picture.width * scale), round(picture.height * scale)))
            x, y = (i % 8) * 200, (i // 8) * 210
            sheet.paste(picture, (x, y + 35))
            draw.text((x + 3, y + 3), f"#{i + 1} {row['id']}", fill="white")
            draw.text((x + 3, y + 18), f"t={row['seconds']:.2f}", fill="white")
        sheet.save(args.out / f"segment_{segment}.jpg", quality=95)
        records.extend(rows)
    manifest = {"selection": "all cached person boxes nearest 5 and 20 seconds; earlier frame breaks ties",
                "predictions_visible_during_labeling": False, "independently_adjudicated": False,
                "reviewer": None, "input_sha256": hashes, "records": records}
    (args.out / "labels.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"samples": len(records), "segments": args.segments, "directory": str(args.out)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
