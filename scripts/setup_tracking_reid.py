"""Download and verify the pinned official OSNet checkpoint, without replacing files."""
from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

from app.tracking.deepocsort import DEFAULT_MODEL, verified_model_path

MODEL_ID = "1HT7RQ86AqFXigF08X_59t9zMTEwVTuFf"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path(DEFAULT_MODEL))
    args = parser.parse_args()
    target = args.out.resolve()
    if target.exists():
        print(f"Verified: {verified_model_path(str(target))}")
        return
    import gdown

    target.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix="osnet-download-", suffix=".part", dir=target.parent)
    os.close(fd)
    partial = Path(name)
    try:
        result = gdown.download(id=MODEL_ID, output=str(partial), quiet=False)
        if result is None:
            raise RuntimeError("Official model download failed")
        verified_model_path(str(partial))
        # Hard-link creation is atomic and refuses an existing destination.
        # Both files are on the same filesystem; no overwrite race with a worker.
        os.link(partial, target)
    finally:
        partial.unlink(missing_ok=True)
    print(f"Verified: {target}")


if __name__ == "__main__":
    main()
