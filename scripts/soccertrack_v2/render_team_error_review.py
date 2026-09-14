"""Render deterministic review crops from a team-error audit (venv-cv).

Selects the first/middle/last spatial mismatch and a middle spatial agreement
from the largest error tracks. This deliberately biased review sample must not
be used as an overall classifier accuracy benchmark. No labels are inferred.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def review_samples(report: dict, split: str, top_tracks: int) -> list[list[dict]]:
    groups = []
    for group in report["splits"][split]["ranked_error_tracks"][:top_tracks]:
        records = [r for r in report["records"]
                   if (r["segment"], r["track"]) == (group["segment"], group["track"])]
        wrong = [r for r in records if r["predicted_team"] is not None and r["predicted_team"] != r["gt_team"]]
        correct = [r for r in records if r["predicted_team"] == r["gt_team"]]
        if not wrong:
            continue
        selected = [wrong[0], wrong[len(wrong) // 2], wrong[-1]]
        if correct:
            selected.append(correct[len(correct) // 2])
        unique = {r["seconds"]: r for r in selected}
        groups.append(list(unique.values()))
    return groups


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True, help="new directory for image and sample manifest")
    parser.add_argument("--split", choices=("development", "control"), default="development")
    parser.add_argument("--top-tracks", type=int, default=6)
    args = parser.parse_args()
    if args.out.exists() or args.top_tracks <= 0:
        parser.error("choose a new output directory and a positive track count")
    report = json.loads(args.audit.read_text(encoding="utf-8"))
    groups = review_samples(report, args.split, args.top_tracks)
    if not groups:
        parser.error("no spatial mismatches to review")
    import cv2
    from PIL import Image, ImageDraw

    sheet = Image.new("RGB", (1200, len(groups) * 260), "#111827")
    draw = ImageDraw.Draw(sheet)
    for row, records in enumerate(groups):
        for col, record in enumerate(records):
            cap = cv2.VideoCapture(record["video"])
            cap.set(cv2.CAP_PROP_POS_MSEC, record["video_seconds"] * 1000)
            ok, frame = cap.read()
            cap.release()
            if not ok:
                raise ValueError(f"cannot read {record['video']} at {record['video_seconds']}")
            x1, y1, x2, y2 = [round(v) for v in record["bbox"]]
            left, top = max(0, x1 - 35), max(0, y1 - 25)
            crop = cv2.cvtColor(frame[top:y2 + 25, left:x2 + 35], cv2.COLOR_BGR2RGB)
            picture = Image.fromarray(crop)
            ImageDraw.Draw(picture).rectangle((x1 - left, y1 - top, x2 - left, y2 - top),
                                             outline="#fbbf24", width=1)
            scale = min(280 / picture.width, 200 / picture.height)
            picture = picture.resize((round(picture.width * scale), round(picture.height * scale)))
            x, y = col * 300, row * 260
            sheet.paste(picture, (x, y + 48))
            draw.text((x + 3, y + 3), f"seg {record['segment']} track {record['track']} t={record['seconds']:.1f}", fill="white")
            draw.text((x + 3, y + 20), f"pred {record['predicted_team']} | spatial GT {record['gt_team']} | {record['distance_m']:.1f}m", fill="white")
    args.out.mkdir(parents=True)
    sheet.save(args.out / "review.jpg", quality=95)
    manifest = {"split": args.split, "selection": "first/middle/last mismatch and middle agreement; deduplicated",
                "warning": "Biased diagnostic sample, not an independent accuracy benchmark.",
                "groups": groups}
    (args.out / "samples.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"directory": str(args.out), "samples": sum(len(g) for g in groups)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
