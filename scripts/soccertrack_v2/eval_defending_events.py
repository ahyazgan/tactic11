"""GSR'si olmayan maçta telestrasyonun savunan takımını dokunuş olaylarına karşı ölç (venv-cv).

`eval_telestration --possession-events` GSR oyuncu tablosu ister; bu araç yalnız
takip karelerini ve olay eşlemesini (`derive_event_mapping`) kullanır:

- Telestratör takip kareleriyle kare kare koşar (üretimdeki gibi); hücum yönü
  eşlemeden gelir: çevrilmemiş olay takımı ilk yarıda saha x'i artan yöne hücum eder.
- Olay takımı → takip takımı eşlemenin `team_side` alanından (dokunan oyuncunun
  takip takımı çoğunluğu).
- Ölçüt `eval_telestration` ile aynı: çizilen karelerde savunan takım, aynı takımın
  ardışık iki dokunuşu arası (≤ 4 sn) sahipliğin tersi mi.

    venv-cv\\Scripts\\python.exe -X utf8 -m scripts.soccertrack_v2.eval_defending_events \\
        --frames "data/tracking/live/990741/frames/seg_*.json" \\
        --mapping docs/measurements/ball-events-mapping-132877.json \\
        --calibration data/tracking/calibrations/soccertrack_v2_132877_landmarks.json --out rapor.json
"""
from __future__ import annotations

import argparse
import glob
import json
from collections import Counter
from pathlib import Path

from app.domain import TrackingFrame
from app.tracking.calibration import PitchCalibration
from app.tracking.telestration import Telestrator, spots_from_frame
from scripts.soccertrack_v2.evaluate_ball_events import (
    EventMapping,
    load_touches,
    possession_intervals,
)


def home_direction(mapping: EventMapping) -> int:
    """Takip ev sahibinin (taraf 0) ilk yarı hücum yönü: +1 saha x artan, −1 azalan."""
    home_team = next(team for team, side in mapping.team_side.items() if side == 0)
    return -1 if mapping.flip[home_team] else 1


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--frames", required=True, help="frames JSON (glob)")
    p.add_argument("--mapping", type=Path, required=True)
    p.add_argument("--calibration", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    payloads = [json.loads(Path(f).read_text(encoding="utf-8")) for f in sorted(glob.glob(args.frames))]
    home, away = payloads[0]["home_team_external_id"], payloads[0]["away_team_external_id"]
    frames = sorted((TrackingFrame.model_validate(f) for d in payloads for f in d["frames"]), key=lambda f: f.minute)
    calib = PitchCalibration.load(args.calibration)
    mapping = EventMapping.load(args.mapping)
    seconds = [f.minute * 60.0 for f in frames]
    steps = sorted(b - a for a, b in zip(seconds, seconds[1:], strict=False) if b > a)
    tele = Telestrator(1.0 / steps[len(steps) // 2], home_direction(mapping))
    intervals = possession_intervals(load_touches(mapping), mapping.team_side)
    gates: Counter[str] = Counter()
    in_poss = drawn = correct = 0
    for f, t in zip(frames, seconds, strict=True):
        players, ball, owner = spots_from_frame(f, home, away, calib)
        tele.marks(players, ball, calib, owner)
        gates[tele.last_gate or ""] += 1
        side = next((s for a, b, s in intervals if a <= t < b), None)
        if side is None:
            continue
        in_poss += 1
        if tele.last_gate == "drawn" and tele.last_defending is not None:
            drawn += 1
            correct += tele.last_defending == 1 - side
    report = {"frames_files": len(payloads), "frames": len(frames), "home_attack_direction": home_direction(mapping),
              "gates": dict(gates), "drawn_pct": round(100.0 * gates["drawn"] / max(1, len(frames)), 1),
              "label": tele.label,
              "defending_vs_events": {"frames_in_possession": in_poss, "drawn": drawn, "correct": correct,
                                      "accuracy_pct": round(100.0 * correct / max(1, drawn), 1),
                                      "correct_of_possession_pct": round(100.0 * correct / max(1, in_poss), 1)}}
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
