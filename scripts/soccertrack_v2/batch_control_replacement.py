"""Replace an out-of-range empty night clip before opening any night pixels."""
from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from scripts.soccertrack_v2 import batch_control as original

FREEZE = Path("docs/measurements/torch-batch-night-replacement-decision.json")
ROOT = Path("data/tracking/bench/torch_batch_control_replacement_v1")
PLAN = Path("docs/TORCH-GRUPLAMA-GECE-KONTROL-DUZELTMESI.md")


def freeze() -> None:
    import cv2

    if FREEZE.exists() or ROOT.exists():
        raise ValueError("Replacement must be frozen before extraction")
    decision = original.verify()
    empty = original.ROOT / "night/source.mp4"
    cap = cv2.VideoCapture(str(empty))
    frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    opened = cap.isOpened()
    cap.release()
    if not empty.exists() or opened or frames > 0 or (empty.parent / "legacy.log").exists():
        raise ValueError("Original night must have no frames or model run")
    spec = decision["groups"]["night"]
    cap = cv2.VideoCapture(spec["video"])
    count, fps = cap.get(cv2.CAP_PROP_FRAME_COUNT), cap.get(cv2.CAP_PROP_FPS)
    cap.release()
    if fps != 25 or count != 67375 or spec["start"] < count / fps:
        raise ValueError("Expected out-of-range original source decision")
    decision["created_utc"] = datetime.now(UTC).isoformat()
    decision["amendment"] = dict(original_freeze=str(original.FREEZE),
        original_freeze_sha256=original.digest(original.FREEZE), original_start=spec["start"],
        empty_frame_count_metadata=frames, empty_capture_opened=opened, source_frames=count, source_fps=fps,
        reason="Original night start exceeded source duration; no night pixels or inference opened",
        candidate_code_changed=False)
    decision["groups"] = {"night": dict(spec, start=2580)}
    decision["code_sha256_lf"][str(Path(__file__))] = original.code_hash(Path(__file__))
    for path in (PLAN, original.FREEZE, empty):
        decision["input_sha256"][str(path)] = original.digest(path)
    original.write_new(FREEZE, decision)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["freeze", "run", "verify"])
    args = parser.parse_args()
    if args.action == "freeze":
        freeze()
        return
    original.FREEZE, original.ROOT = FREEZE, ROOT
    decision = original.verify()
    if args.action == "run":
        original.run("night", decision)


if __name__ == "__main__":
    main()
