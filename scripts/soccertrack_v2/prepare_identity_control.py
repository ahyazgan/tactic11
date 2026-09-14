"""Prepare fixed, blinded raw-detection kit and person-association review.

Run only after the production decision is frozen. Predictions never select or
label these crops: all person detections at the fixed source frames are kept.
The output contains no tracker IDs, team predictions, or model-dependent links.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

START_FRAMES = (374, 686)
PAIR_DELTA_FRAMES = 30
BOXES_PER_PAGE = 24


def digest(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 << 20), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def context_frames(start: int) -> list[int]:
    return sorted(set(range(start - 8, start + 39, 4)) | {start, start + 30, start + 38})


def select_raw_frames(payload: dict[str, Any], segment: int) -> dict[int, list[dict[str, Any]]]:
    """Read only raw detector boxes, using exact frame indices (never nearest)."""
    if "segment" in payload and int(payload["segment"]) != segment:
        raise ValueError("cache segment disagrees with requested segment")
    required = {frame for start in START_FRAMES for frame in context_frames(start)}
    selected = {}
    for sample in payload["samples"]:
        frame = int(sample["frame_idx"])
        if frame not in required:
            continue
        if frame in selected:
            raise ValueError(f"duplicate source frame: {segment}/{frame}")
        records = payload["detected_persons"][str(sample["order"])]
        boxes = []
        for index, record in enumerate(records):
            box = np.asarray(record["box"], dtype=float)
            if box.shape != (4,) or not np.isfinite(box).all() or np.any(box[2:] <= box[:2]):
                raise ValueError(f"invalid detector box: {segment}/{frame}/{index}")
            boxes.append({"id": f"{segment}-{frame}-d{index}", "segment": segment,
                          "frame_idx": frame, "detector_index": index,
                          "bbox": box.tolist()})
        selected[frame] = boxes
    missing = sorted(required - set(selected))
    if missing:
        raise ValueError(f"exact source frames missing: {segment}: {missing}")
    return selected


def review_manifests(selected: dict[int, list[dict[str, Any]]], video: str) -> tuple[list, list, list]:
    starts, observations, pairs = [], [], []
    for frame in START_FRAMES:
        end = frame + PAIR_DELTA_FRAMES
        starts.extend({**row, "video": video, "seconds": frame / 25., "kit": None}
                      for row in selected[frame])
        observations.extend({**row, "video": video, "seconds": frame_id / 25.}
                            for frame_id in (frame, end) for row in selected[frame_id])
        for row in selected[frame]:
            pairs.append({"left": row["id"], "right": None, "relation": None,
                          "endpoint_frame_idx": end,
                          "endpoint_candidates": [candidate["id"] for candidate in selected[end]],
                          "source_visibility": None, "visual_basis": None})
    return starts, observations, pairs


def _write_json(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def _save_jpg(path: Path, frame: np.ndarray) -> None:
    import cv2

    if not cv2.imwrite(str(path), frame, [cv2.IMWRITE_JPEG_QUALITY, 88]):
        raise ValueError(f"cannot write review image: {path}")


def _draw_box(image: np.ndarray, row: dict, *, left: int = 0, top: int = 0,
              selected: bool = False) -> None:
    import cv2

    x1, y1, x2, y2 = map(round, row["bbox"])
    a, b = (x1 - left, y1 - top), (x2 - left, y2 - top)
    color = (0, 255, 255) if selected else (255, 230, 150)
    cv2.rectangle(image, a, b, color, 1)
    label = f"d{row['detector_index']}"
    position = (max(1, a[0]), max(12, a[1] - 3))
    cv2.putText(image, label, position, cv2.FONT_HERSHEY_SIMPLEX, .4, (0, 0, 0), 3)
    cv2.putText(image, label, position, cv2.FONT_HERSHEY_SIMPLEX, .4, color, 1)


def _crop_pages(frame: np.ndarray, records: list[dict], *, segment: int,
                frame_idx: int, out: Path) -> list[str]:
    import cv2

    names = []
    for page in range(max(1, math.ceil(len(records) / BOXES_PER_PAGE))):
        canvas = np.full((4 * 230, 6 * 256, 3), 245, np.uint8)
        subset = records[page * BOXES_PER_PAGE:(page + 1) * BOXES_PER_PAGE]
        for index, row in enumerate(subset):
            x1, y1, x2, y2 = map(round, row["bbox"])
            left, top = max(0, x1 - 16), max(0, y1 - 14)
            right, bottom = min(frame.shape[1], x2 + 16), min(frame.shape[0], y2 + 14)
            crop = frame[top:bottom, left:right].copy()
            if not crop.size:
                raise ValueError(f"box does not intersect source image: {row['id']}")
            _draw_box(crop, row, left=left, top=top, selected=True)
            scale = min(246 / crop.shape[1], 188 / crop.shape[0])
            crop = cv2.resize(crop, (max(1, round(crop.shape[1] * scale)),
                                     max(1, round(crop.shape[0] * scale))))
            x, y = index % 6 * 256, index // 6 * 230
            canvas[y + 35:y + 35 + crop.shape[0], x + 5:x + 5 + crop.shape[1]] = crop
            cv2.putText(canvas, row["id"], (x + 5, y + 23), 0, .55, (0, 0, 0), 1)
        name = f"s{segment:04d}-f{frame_idx:04d}-page{page + 1:02d}.jpg"
        _save_jpg(out / name, canvas)
        names.append(name)
    return names


def _strip(frames: dict[int, np.ndarray], selected: dict[int, list[dict]],
           seed: dict, out: Path) -> str:
    import cv2

    start = seed["frame_idx"]
    indices = context_frames(start)
    x1, y1, x2, y2 = seed["bbox"]
    # A fixed region follows no predicted track. Wide context allows a person
    # to emerge after occlusion while retaining nearby competing detections.
    width = max(260., 10 * (x2 - x1), 6 * (y2 - y1))
    height = max(156., 4 * (y2 - y1))
    source_h, source_w = frames[start].shape[:2]
    left = max(0, round((x1 + x2) / 2 - width / 2))
    top = max(0, round((y1 + y2) / 2 - height / 2))
    right, bottom = min(source_w, left + round(width)), min(source_h, top + round(height))
    canvas = np.full((math.ceil(len(indices) / 4) * 256, 4 * 400, 3), 245, np.uint8)
    for index, frame_idx in enumerate(indices):
        crop = frames[frame_idx][top:bottom, left:right].copy()
        if not crop.size:
            raise ValueError(f"empty context for {seed['id']}")
        for row in selected[frame_idx]:
            a, b, c, d = row["bbox"]
            if c > left and a < right and d > top and b < bottom:
                _draw_box(crop, row, left=left, top=top, selected=row["id"] == seed["id"])
        scale = min(400 / crop.shape[1], 225 / crop.shape[0])
        crop = cv2.resize(crop, (max(1, round(crop.shape[1] * scale)),
                                 max(1, round(crop.shape[0] * scale))))
        x, y = index % 4 * 400, index // 4 * 256
        inset_x = x + (400 - crop.shape[1]) // 2
        inset_y = y + 31 + (225 - crop.shape[0]) // 2
        canvas[inset_y:inset_y + crop.shape[0], inset_x:inset_x + crop.shape[1]] = crop
        role = " START" if frame_idx == start else " END" if frame_idx == start + 30 else ""
        cv2.putText(canvas, f"F{frame_idx} {frame_idx / 25:.2f}s{role}",
                    (x + 4, y + 23), 0, .6, (0, 0, 0), 1)
    name = f"association-{seed['id']}.jpg"
    _save_jpg(out / name, canvas)
    return name


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--segments", type=int, nargs="+", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("choose a fresh output directory; preserve earlier labels and review evidence")
    if len(set(args.segments)) != len(args.segments):
        parser.error("segments must be unique")
    import cv2

    args.out.mkdir(parents=True)
    kit_records, observations, pairs, manifests = [], [], [], []
    input_hashes = {}
    for segment in args.segments:
        cache = args.cache / f"seg_{segment:04d}.json"
        video = args.source / f"seg_{segment:04d}.mp4"
        payload = json.loads(cache.read_text(encoding="utf-8"))
        selected = select_raw_frames(payload, segment)
        input_hashes[str(cache)], input_hashes[str(video)] = digest(cache), digest(video)
        cap = cv2.VideoCapture(str(video))
        if not cap.isOpened() or abs(cap.get(cv2.CAP_PROP_FPS) - 25.) > .01:
            cap.release()
            raise ValueError(f"review protocol requires the selected25fps source: {video}")
        frames = {}
        try:
            # Decode monotonically, keeping only selected frames. Repeated seeks
            # per person would otherwise decode the same GOP hundreds of times.
            for frame_idx in range(max(selected) + 1):
                if frame_idx in selected:
                    ok, frame = cap.read()
                    if not ok:
                        raise ValueError(f"cannot decode exact frame {frame_idx} from {video}")
                    frames[frame_idx] = frame
                elif not cap.grab():
                    raise ValueError(f"cannot advance to frame {frame_idx} from {video}")
        finally:
            cap.release()
        records, obs, links = review_manifests(selected, str(video))
        kit_records.extend(records)
        observations.extend(obs)
        pairs.extend(links)
        assets = []
        for frame_idx in sorted({f for start in START_FRAMES for f in (start, start + 30)}):
            overview = frames[frame_idx].copy()
            for row in selected[frame_idx]:
                _draw_box(overview, row)
            name = f"s{segment:04d}-f{frame_idx:04d}-overview.jpg"
            _save_jpg(args.out / name, overview)
            assets.append(name)
            assets.extend(_crop_pages(frames[frame_idx], selected[frame_idx],
                                      segment=segment, frame_idx=frame_idx, out=args.out))
        for seed in records:
            name = _strip(frames, selected, seed, args.out)
            seed["association_review"] = name
            assets.append(name)
        manifests.append({"segment": segment, "video": str(video), "cache": str(cache),
                          "source_size": [frames[START_FRAMES[0]].shape[1], frames[START_FRAMES[0]].shape[0]],
                          "decoded_review_frames": sorted(frames),
                          "start_boxes": len(records), "start_and_end_boxes": len(obs),
                          "assets_sha256": {name: digest(args.out / name) for name in assets}})
        print(f"segment{segment}: {len(records)} start boxes; {len(assets)} blinded review images", flush=True)
    common = {"protocol": "docs/SABIT-KAMERA-KONTROL-ETIKETLEME.md",
              "selection": "all raw person detections at374/686; association endpoints404/716",
              "predictions_visible_during_labeling": False, "independently_adjudicated": False,
              "reviewer": None, "input_sha256": input_hashes}
    _write_json(args.out / "labels.json", {**common, "records": kit_records})
    _write_json(args.out / "pairs.json", {**common, "observations": observations, "pairs": pairs,
                "instructions": "Fill right/relation only from visible person continuity; uncertain and source-missing cases stay explicit. Add the protocol's nearest clearly different person pair separately. Do not use tracker IDs."})
    _write_json(args.out / "manifest.json", {**common, "segments": manifests,
                "script_sha256": hashlib.sha256(Path(__file__).read_text(encoding="utf-8").encode()).hexdigest(),
                "protocol_sha256": digest(Path(common["protocol"]))})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
