"""Yayın çapası geliştirme kapıları (venv-cv). Ön kayıt: docs/measurements/broadcast-anchor-preregistration.json.

    venv-cv\\Scripts\\python.exe -X utf8 -m scripts.broadcast_anchor_exam g1
    venv-cv\\Scripts\\python.exe -X utf8 -m scripts.broadcast_anchor_exam g2
    venv-cv\\Scripts\\python.exe -X utf8 -m scripts.broadcast_anchor_exam frames --match gamba_kashiwa --out <klasör>
    venv-cv\\Scripts\\python.exe -X utf8 -m scripts.broadcast_anchor_exam tally --dir <klasör>
    venv-cv\\Scripts\\python.exe -X utf8 -m scripts.broadcast_anchor_exam audit --dir <klasör> --out <klasör>

G1: elle gerçek duruştan çizilmiş kusursuz çizgi maskesinde yöntem doğruyu buluyor mu?
G2: aynı karelerde gerçek çizgi maskesiyle. `frames` + `tally`: 5 geliştirme maçında main kabul
oranı ve G3 (other karelerde kabul). `frames`, `tally` ve `audit` yalnız geliştirme maçlarını okur.

Kontrol, ön kayıt sırasıyla: control-inspect, control-sheets, control-pick, control-grid, sonra bir
kez control-run. control-run kod hash'i tutmazsa veya sonuç dosyası varsa koşmaz, kare dökümü üretmez.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from statistics import median

from app.tracking.broadcast_anchor import (
    GRASS_HSV_HIGH,
    GRASS_HSV_LOW,
    daylight_line_mask,
    find_broadcast_anchor,
)
from scripts.calibration_funnel import (
    MATCH_GROUP,
    homography_from_points,
    ideal_dist_map,
    other_frames,
    pick_frames,
    probe_distance_m,
    refined_pose,
    video_of,
)
from scripts.shot_exam import (
    SHEET_COLS,
    SHEET_ROWS,
    TILE_H,
    TILE_W,
    sampled_frames,
    wilson,
    write_sheet,
)

POINTS = Path("docs/measurements/daylight-calibration-truth-points.json")
G1_MIN_ACCEPTED, G1_MAX_MEDIAN_M, G1_MAX_ANY_M = 13, 1.0, 5.0
G2_MIN_ACCEPTED, G2_MAX_MEDIAN_M, G2_MAX_ANY_M = 5, 2.0, 5.0
G3_MAX_OTHER_RATE = 0.05
MIN_GRASS_RATIO = 0.50
PLAN = Path("docs/measurements/broadcast-anchor-preregistration.json")
CONTROL_TRUTH_PER_MATCH = 30
C1_MIN_TOTAL, C1_MIN_PER_MATCH = 0.30, 0.20
C2_MAX_MEDIAN_M = 2.0
C3_WRONG_M, C3_MAX_RATE = 5.0, 0.05
C4_MAX_RATE = 0.05
C5_MIN_SAMPLE = 15


def to_gray(frame):
    import cv2

    return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)


def truth_frames():
    """(maç, kare no, BGR, gerçek duruş); işaretlenemeyen kareler atlanır."""
    spec = json.loads(POINTS.read_text(encoding="utf-8"))
    for match, frames_spec in spec["frames"].items():
        wanted = {int(k): v["points"] for k, v in frames_spec.items() if v.get("points")}
        for i, frame in sampled_frames(video_of(match)):
            if i in wanted:
                yield match, i, frame, refined_pose(frame, homography_from_points(wanted[i]))


def gate(name: str, rows: list[dict], min_accepted: int, max_median: float, max_any: float) -> None:
    accepted = [r for r in rows if r["accepted"]]
    errors = [r["error_m"] for r in accepted]
    med = median(errors) if errors else None
    worst = max(errors) if errors else None
    passed = len(accepted) >= min_accepted and med is not None and med <= max_median and worst <= max_any
    print(f"{name}: kabul {len(accepted)}/{len(rows)}, medyan hata {med}, en kötü {worst} → "
          f"{'GEÇTİ' if passed else 'KALDI'}")


def truth_row(match: str, i: int, res, pose, size: tuple[int, int], seconds: float) -> dict:
    found = res.best_homography
    row = {"match": match, "frame": i, "accepted": res.accepted,
           "error_m": round(probe_distance_m(found, pose, size), 2) if found is not None else None,
           "note": res.note, "inlier": res.inlier, "explained": res.explained,
           "hypotheses": res.hypotheses, "seconds": round(seconds, 2)}
    print(json.dumps(row, ensure_ascii=False), flush=True)
    return row


def g1() -> int:
    rows = []
    for match, i, frame, pose in truth_frames():
        size = (frame.shape[1], frame.shape[0])
        dist, _px = ideal_dist_map(pose, size)
        start = time.perf_counter()
        res = find_broadcast_anchor(dist <= 0.5)
        rows.append(truth_row(match, i, res, pose, size, time.perf_counter() - start))
    gate("G1", rows, G1_MIN_ACCEPTED, G1_MAX_MEDIAN_M, G1_MAX_ANY_M)
    return 0


def g2() -> int:
    rows = []
    for match, i, frame, pose in truth_frames():
        size = (frame.shape[1], frame.shape[0])
        start = time.perf_counter()
        res = find_broadcast_anchor(daylight_line_mask(frame), to_gray(frame))
        rows.append(truth_row(match, i, res, pose, size, time.perf_counter() - start))
    gate("G2", rows, G2_MIN_ACCEPTED, G2_MAX_MEDIAN_M, G2_MAX_ANY_M)
    return 0


def frames(match: str, out: Path) -> int:
    """Maçın tüm örnek kareleri: etiket + kabul. Çim oranı düşük kare yönteme hiç girmez."""
    import cv2
    import numpy as np

    out.mkdir(parents=True, exist_ok=True)
    others = other_frames(match)
    rows = []
    for i, frame in sampled_frames(video_of(match)):
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        grass = float((cv2.inRange(hsv, np.array(GRASS_HSV_LOW), np.array(GRASS_HSV_HIGH)) > 0).mean())
        res = None if grass < MIN_GRASS_RATIO else find_broadcast_anchor(daylight_line_mask(frame), to_gray(frame))
        rows.append({"match": match, "frame": i, "label": "other" if i in others else "main",
                     "grass": round(grass, 3), "accepted": bool(res and res.accepted),
                     "note": res.note if res else "çim oranı düşük",
                     "inlier": res.inlier if res else 0.0, "explained": res.explained if res else 0.0,
                     "homography": res.homography.tolist() if res and res.accepted else None})
    (out / f"{match}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"{match}: {len(rows)} kare")
    return 0


def tally(folder: Path) -> int:
    rows: list[dict] = []
    for match in MATCH_GROUP:
        part = json.loads((folder / f"{match}.json").read_text(encoding="utf-8"))
        rows += part
        for label in ("main", "other"):
            sel = [r for r in part if r["label"] == label]
            print(f"{match} {label}: kabul {sum(r['accepted'] for r in sel)}/{len(sel)}")
    for label in ("main", "other"):
        sel = [r for r in rows if r["label"] == label]
        hits = sum(r["accepted"] for r in sel)
        low, high = wilson(hits, len(sel))
        print(f"TOPLAM {label}: {hits}/{len(sel)} = %{100 * hits / len(sel):.1f} "
              f"(Wilson %{100 * low:.1f}-%{100 * high:.1f})")
    other = [r for r in rows if r["label"] == "other"]
    rate = sum(r["accepted"] for r in other) / len(other)
    print(f"G3: other kabul %{100 * rate:.1f} → {'GEÇTİ' if rate <= G3_MAX_OTHER_RATE else 'KALDI'}")
    return 0


def audit(folder: Path, out: Path, per_label: int) -> int:
    """Kabul edilen karelerden eşit aralıklı örnek: göz denetimi için model bindirmesi."""
    import cv2
    import numpy as np

    from scripts.calibration_funnel import write_overlay

    rows: list[dict] = []
    for match in MATCH_GROUP:
        rows += [r for r in json.loads((folder / f"{match}.json").read_text(encoding="utf-8")) if r["accepted"]]
    mains = [r for r in rows if r["label"] == "main"]
    picked = [mains[int((k + 0.5) * len(mains) / per_label)] for k in range(min(per_label, len(mains)))]
    picked += [r for r in rows if r["label"] == "other"]
    out.mkdir(parents=True, exist_ok=True)
    tiles = []
    for r in picked:
        for i, frame in sampled_frames(video_of(r["match"])):
            if i == r["frame"]:
                path = out / f"{r['match']}_{i}.jpg"
                write_overlay(path, frame, np.array(r["homography"]))
                tile = cv2.resize(cv2.imread(str(path)), (640, 360))
                cv2.putText(tile, f"{r['label']} {r['match'][:5]} {i}", (120, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                tiles.append(tile)
                break
    tiles += [np.zeros_like(tiles[0])] * (-len(tiles) % 3)
    for page in range(0, len(tiles), 12):
        chunk = tiles[page:page + 12]
        sheet = np.vstack([np.hstack(chunk[k:k + 3]) for k in range(0, len(chunk), 3)])
        cv2.imwrite(str(out / f"sheet_{page // 12}.jpg"), sheet, [cv2.IMWRITE_JPEG_QUALITY, 85])
    print(f"{len(picked)} kare, {len(tiles) // 12 + bool(len(tiles) % 12)} sayfa")
    return 0


def control_videos() -> dict[str, Path]:
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    return {name: Path(item["file"]) for name, item in plan["control_matches"].items()}


def sha256_lf(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def verify_freeze() -> None:
    frozen = json.loads(PLAN.read_text(encoding="utf-8"))["freeze_before_control"]["code_sha256_lf"]
    for name, expected in frozen.items():
        if sha256_lf(Path(name)) != expected:
            raise SystemExit(f"dondurulmuş kod değişmiş: {name}; kontrol koşulmaz")


def control_inspect() -> int:
    """Yalnız sayı: görüntü yazmaz, gündüz kontrolü içindir."""
    for name, video in control_videos().items():
        grays = [float(to_gray(f).mean()) for _, f in sampled_frames(video)]
        print(f"{name}: {len(grays)} örnek, parlaklık medyan {median(grays):.0f}, "
              f"en düşük {min(grays):.0f}, en yüksek {max(grays):.0f}")
    return 0


def control_sheets(out: Path) -> int:
    """Etiket sayfaları: numaralı küçük kareler, yöntem çıktısı içermez."""
    import cv2
    import numpy as np

    out.mkdir(parents=True, exist_ok=True)
    per_sheet = SHEET_COLS * SHEET_ROWS
    for name, video in control_videos().items():
        tiles: list[np.ndarray] = []
        page = 0
        for i, frame in sampled_frames(video):
            tile = cv2.resize(frame, (TILE_W, TILE_H), interpolation=cv2.INTER_AREA)
            cv2.rectangle(tile, (0, 0), (70, 34), (0, 0, 0), -1)
            cv2.putText(tile, str(i), (6, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.85, (0, 255, 255), 2)
            tiles.append(tile)
            if len(tiles) == per_sheet:
                write_sheet(out / f"{name}_{page:02d}.jpg", tiles)
                page, tiles = page + 1, []
        if tiles:
            write_sheet(out / f"{name}_{page:02d}.jpg", tiles)
    return 0


def control_pick(labels_path: Path) -> int:
    """Gerçek duruş işaretlenecek kareler: yalnız etiket dizisinden, maç başına 30."""
    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    for name, video in control_videos().items():
        count = sum(1 for _ in sampled_frames(video))
        print(name, pick_frames(count, set(labels[name]["other"]), CONTROL_TRUTH_PER_MATCH))
    return 0


def control_grid(match: str, frame_no: int, out: Path) -> int:
    import cv2

    for i, frame in sampled_frames(control_videos()[match]):
        if i == frame_no:
            for x in range(0, frame.shape[1], 100):
                cv2.line(frame, (x, 0), (x, frame.shape[0]), (0, 220, 220), 1)
                cv2.putText(frame, str(x), (x + 2, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1)
            for y in range(0, frame.shape[0], 100):
                cv2.line(frame, (0, y), (frame.shape[1], y), (0, 220, 220), 1)
                cv2.putText(frame, str(y), (2, y + 14), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1)
            cv2.imwrite(str(out), frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            return 0
    raise SystemExit("kare bulunamadı")


def evaluate_control(rows: list[dict]) -> dict:
    """Ön kayıttaki C1-C5. Satır: match, label, accepted, error_m (gerçek duruş yoksa None)."""
    out: dict = {"per_match": {}}
    for match in sorted({r["match"] for r in rows}):
        sel = [r for r in rows if r["match"] == match]
        out["per_match"][match] = rate_block(sel)
    total = rate_block(rows)
    errors = [r["error_m"] for r in rows if r["accepted"] and r["label"] == "main" and r["error_m"] is not None]
    wrong = sum(e > C3_WRONG_M for e in errors)
    med = median(errors) if errors else None
    checks = {
        "C1_main_acceptance": total["main"]["rate"] >= C1_MIN_TOTAL
        and all(m["main"]["rate"] >= C1_MIN_PER_MATCH for m in out["per_match"].values()),
        "C2_accuracy": med is not None and med <= C2_MAX_MEDIAN_M,
        "C3_wrong_accept_main": bool(errors) and wrong / len(errors) <= C3_MAX_RATE,
        "C4_wrong_accept_other": total["other"]["rate"] <= C4_MAX_RATE,
        "C5_minimum_sample": len(errors) >= C5_MIN_SAMPLE,
    }
    out.update(total=total, truth_accepted=len(errors), median_error_m=med, wrong_gt_5m=wrong,
               worst_error_m=max(errors) if errors else None, checks=checks,
               verdict="GEÇTİ" if all(checks.values()) else "KALDI")
    return out


def rate_block(rows: list[dict]) -> dict:
    block = {}
    for label in ("main", "other"):
        sel = [r for r in rows if r["label"] == label]
        hits = sum(r["accepted"] for r in sel)
        low, high = wilson(hits, len(sel))
        block[label] = {"accepted": hits, "n": len(sel), "rate": round(hits / max(len(sel), 1), 3),
                        "wilson95": [round(low, 3), round(high, 3)]}
    return block


def control_run(labels_path: Path, points_path: Path, out: Path) -> int:
    """TEK koşu. Kare dökümü üretmez, yalnız toplamları yazar; aynı kontrolle ikinci deneme yoktur."""
    import cv2
    import numpy as np

    verify_freeze()
    if out.exists():
        raise SystemExit(f"sonuç zaten var: {out}; kontrol ikinci kez koşulmaz")
    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    points = json.loads(points_path.read_text(encoding="utf-8"))["frames"]
    rows = []
    for name, video in control_videos().items():
        others = set(labels[name]["other"])
        marked = {int(k): v["points"] for k, v in points[name].items() if v.get("points")}
        for i, frame in sampled_frames(video):
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            grass = float((cv2.inRange(hsv, np.array(GRASS_HSV_LOW), np.array(GRASS_HSV_HIGH)) > 0).mean())
            res = None if grass < MIN_GRASS_RATIO else find_broadcast_anchor(daylight_line_mask(frame), to_gray(frame))
            accepted = bool(res and res.accepted)
            error = None
            if accepted and i in marked:
                pose = refined_pose(frame, homography_from_points(marked[i]))
                error = round(probe_distance_m(res.homography, pose, (frame.shape[1], frame.shape[0])), 2)
            rows.append({"match": name, "label": "other" if i in others else "main",
                         "accepted": accepted, "error_m": error})
    result = evaluate_control(rows)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=1))
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("g1")
    sub.add_parser("g2")
    f = sub.add_parser("frames")
    f.add_argument("--match", required=True, choices=sorted(MATCH_GROUP))
    f.add_argument("--out", required=True)
    t = sub.add_parser("tally")
    t.add_argument("--dir", required=True)
    u = sub.add_parser("audit")
    u.add_argument("--dir", required=True)
    u.add_argument("--out", required=True)
    u.add_argument("--per-label", type=int, default=30)
    sub.add_parser("control-inspect")
    cs = sub.add_parser("control-sheets")
    cs.add_argument("--out", required=True)
    cp = sub.add_parser("control-pick")
    cp.add_argument("--labels", required=True)
    cg = sub.add_parser("control-grid")
    cg.add_argument("--match", required=True)
    cg.add_argument("--frame", type=int, required=True)
    cg.add_argument("--out", required=True)
    cr = sub.add_parser("control-run")
    cr.add_argument("--labels", required=True)
    cr.add_argument("--points", required=True)
    cr.add_argument("--out", required=True)
    a = p.parse_args()
    if a.cmd == "control-inspect":
        return control_inspect()
    if a.cmd == "control-sheets":
        return control_sheets(Path(a.out))
    if a.cmd == "control-pick":
        return control_pick(Path(a.labels))
    if a.cmd == "control-grid":
        return control_grid(a.match, a.frame, Path(a.out))
    if a.cmd == "control-run":
        return control_run(Path(a.labels), Path(a.points), Path(a.out))
    if a.cmd == "audit":
        return audit(Path(a.dir), Path(a.out), a.per_label)
    if a.cmd == "g1":
        return g1()
    if a.cmd == "g2":
        return g2()
    if a.cmd == "frames":
        return frames(a.match, Path(a.out))
    return tally(Path(a.dir))


if __name__ == "__main__":
    raise SystemExit(main())
