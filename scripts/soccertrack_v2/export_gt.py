"""Stream SoccerTrack GSR annotations to compact numpy rows, preserving team/role.

Rows: frame, track, team (left=0/right=1/unknown=-1), category, image foot u/v,
pitch x/y (centred metres), box width/height. No video/GT alignment is inferred.
The supplied GSR uses image ids 3000001..3067375; --image-id-base is explicit.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np


def annotations(path: Path):
    """Read the annotations array without loading a multi-GB JSON document."""
    decoder = json.JSONDecoder()
    with path.open(encoding="utf-8") as stream:
        buf = ""
        while True:
            chunk = stream.read(1 << 20)
            if not chunk:
                raise ValueError("annotations array missing")
            buf += chunk
            found = re.search(r'"annotations"\s*:\s*\[', buf)
            if found:
                buf = buf[found.end():]
                break
            buf = buf[-128:]
        pos = 0
        while True:
            while pos < len(buf) and buf[pos] in " \r\n\t,":
                pos += 1
            if pos < len(buf) and buf[pos] == "]":
                return
            try:
                obj, end = decoder.raw_decode(buf, pos)
            except json.JSONDecodeError:
                chunk = stream.read(1 << 20)
                if not chunk:
                    raise ValueError("truncated annotations array") from None
                buf, pos = buf[pos:] + chunk, 0
                continue
            pos = end
            yield obj


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gsr", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--start-frame", type=int, required=True)
    parser.add_argument("--end-frame", type=int, required=True)
    parser.add_argument("--image-id-base", type=int, default=3000000)
    args = parser.parse_args()
    rows = []
    for ann in annotations(args.gsr):
        frame = int(ann["image_id"]) - args.image_id_base
        if not args.start_frame <= frame <= args.end_frame:
            continue
        box, pitch = ann.get("bbox_image"), ann.get("bbox_pitch")
        if not box or not pitch:
            continue
        attrs = ann.get("attributes") or {}
        rows.append((frame, ann.get("track_id", -1),
                     {"left": 0, "right": 1}.get(attrs.get("team"), -1),
                     ann["category_id"], box["x"] + box["w"] / 2,
                     box["y"] + box["h"], pitch["x_bottom_middle"],
                     pitch["y_bottom_middle"], box["w"], box["h"]))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    np.save(args.out, np.asarray(rows, dtype=float).reshape(-1, 10))
    print(json.dumps({"rows": len(rows), "path": str(args.out)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
