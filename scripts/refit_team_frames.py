"""frames JSON klasörüne takım yeniden ataması uygula (app.tracking.team_refit), yeni klasöre yaz.

`scripts.track_live_candidates` çıktısındaki `kit_colors/` ile çalışır; çapa ilk
geçerli segmentten kurulur ve `--anchor` dosyasına yazılır (canlı işçiyle aynı kural).

    venv\\Scripts\\python.exe -m scripts.refit_team_frames --frames data/tracking/live/990752/frames \\
        --kit-colors data/tracking/live/990752/kit_colors --out data/tracking/live/990752/frames_team
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from app.tracking.team_refit import refit_segment


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--frames", type=Path, required=True)
    p.add_argument("--kit-colors", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--anchor", type=Path, default=None, help="çapa dosyası (varsayılan <out>/team_refit_anchor.json)")
    p.add_argument("--feature", default="median", choices=["median", "bright"])
    args = p.parse_args()
    if args.out.resolve() == args.frames.resolve():
        p.error("--out kaynak klasörden farklı olmalı")
    args.out.mkdir(parents=True, exist_ok=True)
    anchor = args.anchor or args.out / "team_refit_anchor.json"
    anchor.unlink(missing_ok=True)
    total: Counter[str] = Counter()
    for path in sorted(args.frames.glob("seg_*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        kit = args.kit_colors / path.name
        if kit.exists():
            stats = refit_segment(payload["frames"], json.loads(kit.read_text(encoding="utf-8")), anchor,
                                  int(payload["home_team_external_id"]), int(payload["away_team_external_id"]),
                                  feature=args.feature)
            total.update({"changed": stats["changed"], "players": stats["players"],
                          "segments_unassigned": int(stats["reason"] is not None)})
        else:
            total["no_kit_colors"] += 1
        (args.out / path.name).write_text(json.dumps(payload), encoding="utf-8")
    print(json.dumps(dict(total)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
