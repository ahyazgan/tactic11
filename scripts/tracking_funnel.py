"""Gündüz yayınında takip kaybını aşamalara böler (venv-cv). Üretim koduna dokunmaz.

Gerçek duruştan başlayan 3 sn 15 fps kliplerde görüntü akışıyla (KLT + RANSAC) referans duruş
zinciri kurar, her kare için kaybı kesme / çizgi çıkarımı / arama diye ayırır ve dört takip
karşı-durumunu koşar. Yalnız geliştirme maçları; görüntüler repoda değildir.

    venv-cv\\Scripts\\python.exe -X utf8 -m scripts.tracking_funnel run \\
        --points docs/measurements/daylight-calibration-truth-points.json --match kyoto_kobe --out <klasör>
    venv-cv\\Scripts\\python.exe -X utf8 -m scripts.tracking_funnel summary --dir <klasör>
    venv-cv\\Scripts\\python.exe -X utf8 -m scripts.tracking_funnel end-grids --dir <klasör> --out <klasör>
    venv-cv\\Scripts\\python.exe -X utf8 -m scripts.tracking_funnel truth --dir <klasör> --marks <json>

Referans duruş gerçek değildir: geri-ileri kapanma hatası her klipte yazılır, uç kare el işaretiyle
ayrıca doğrulanır.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Iterator
from pathlib import Path

import numpy as np

from app.tracking.broadcast_track import (
    FLOW_MIN_INLIERS,
    distance_map,
    flow_step,
    gray_hist,
    is_cut,
)
from scripts.calibration_funnel import (
    MATCH_GROUP,
    TRACK_FPS,
    TRACK_SECONDS,
    homography_from_points,
    probe_distance_m,
    refined_pose,
    tolerance_for,
    video_of,
)

GATE = 0.85                 # üretimin TRACK_MIN_INLIER değeri
LOW_GATE = 0.70
MAX_JUMP_M = 5.0            # üretimin MAX_PITCH_JUMP_M değeri
SEARCH_STEP_PX = 12.0       # üretimin ilk SEARCH_STEPS_PX değeri
NEAR_STEP_PX = 4.0
NEAR_LIMIT_M = 3.0
VARIANTS = ("prod_prev_085", "day_prev_085", "day_flow_085", "day_flow_070")


def clip_frames(video: Path, start_s: float) -> Iterator[np.ndarray]:
    """start_s anından başlayıp TRACK_FPS sıklığında kare verir; sıralı okur, her kareyi aramaz."""
    import cv2

    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS)
    cap.set(cv2.CAP_PROP_POS_MSEC, start_s * 1000.0)
    index = 0
    for k in range(int(TRACK_SECONDS * TRACK_FPS)):
        target = int(round(k / TRACK_FPS * fps))
        frame = None
        while index <= target:
            ok, frame = cap.read()
            index += 1
            if not ok:
                cap.release()
                return
        yield frame
    cap.release()


def best_near(h: np.ndarray, dist_map: np.ndarray, size: tuple[int, int], tolerance: float) -> float:
    """Referans duruşun hemen çevresinde ulaşılabilen inlier: zincirin küçük kayması çizgi kaybı sayılmaz."""
    from app.tracking.homography_fit import refine_homography, score_homography

    fit = refine_homography(h, dist_map, step_px=NEAR_STEP_PX, tolerance_px=tolerance)
    if probe_distance_m(fit.homography, h, size) < NEAR_LIMIT_M:
        return fit.inlier_ratio
    return score_homography(h, dist_map, tolerance_px=tolerance)[1]


def classify_loss(*, cut: bool, reference_inlier: float, produced: bool, gate: float = GATE) -> str:
    """Bir karenin kaybı hangi aşamada: doğru duruşta çizgi yoksa arama suçlanamaz."""
    if cut:
        return "cut"
    if produced:
        return "produced"
    return "line_extraction" if reference_inlier < gate else "search"


class Variant:
    """Üretimin takip kapılarını izleyen küçük döngü: kayıpta son iyi duruş korunur."""

    def __init__(self, h0: np.ndarray, size: tuple[int, int], tolerance: float, *, flow: bool, gate: float):
        self.h, self.size, self.tolerance, self.flow, self.gate = h0, size, tolerance, flow, gate

    def step(self, dist_map: np.ndarray, motion: np.ndarray | None) -> tuple[bool, float]:
        from app.tracking.homography_fit import refine_homography

        start = self.h
        if self.flow and motion is not None:
            start = self.h @ np.linalg.inv(motion)
        fit = refine_homography(start, dist_map, step_px=SEARCH_STEP_PX, tolerance_px=self.tolerance)
        jump = probe_distance_m(fit.homography, self.h, self.size)
        if not fit.accepted or fit.inlier_ratio < self.gate or jump > MAX_JUMP_M:
            if self.flow and motion is not None:
                self.h = start      # akış çizgiden bağımsız yürür: kapı kaçsa da duruş güncel kalır
            return False, fit.inlier_ratio
        self.h = fit.homography
        return True, fit.inlier_ratio


def run_clip(match: str, frame_no: int, points: list[dict]) -> dict:
    import cv2

    from app.tracking.broadcast_anchor import daylight_line_mask
    from app.tracking.pitch_lines import extract_lines
    from app.tracking.shot_filter import classify_shot
    from scripts.shot_exam import STEP_S

    frames = list(clip_frames(video_of(match), frame_no * STEP_S))
    height, width = frames[0].shape[:2]
    size, tol = (width, height), tolerance_for(width)
    h_ref = h_start = refined_pose(frames[0], homography_from_points(points))
    variants = {
        "prod_prev_085": Variant(h_ref, size, tol, flow=False, gate=GATE),
        "day_prev_085": Variant(h_ref, size, tol, flow=False, gate=GATE),
        "day_flow_085": Variant(h_ref, size, tol, flow=True, gate=GATE),
        "day_flow_070": Variant(h_ref, size, tol, flow=True, gate=LOW_GATE),
    }
    rows, grays, motions, cut_seen = [], [], [], False
    prev_gray, prev_hist = None, None
    for k, frame in enumerate(frames):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        hist = gray_hist(gray)
        motion, inliers, ratio, corr = None, FLOW_MIN_INLIERS, 1.0, 1.0
        if prev_gray is not None:
            motion, inliers, ratio = flow_step(prev_gray, gray)
            corr = float(cv2.compareHist(prev_hist, hist, cv2.HISTCMP_CORREL))
            cut_seen = cut_seen or motion is None or is_cut(inliers, corr)
        if motion is not None and not cut_seen:
            h_ref = h_ref @ np.linalg.inv(motion)
            motions.append(motion)
        prod_map = extract_lines(frame).dist_map
        day_map = distance_map(daylight_line_mask(frame))
        row = {
            "k": k, "cut": cut_seen, "main": classify_shot(frame).is_main,
            "flow_inliers": inliers, "flow_ratio": round(ratio, 3), "hist_corr": round(corr, 3),
            "ref_inlier_prod": round(best_near(h_ref, prod_map, size, tol), 3),
            "ref_inlier_day": round(best_near(h_ref, day_map, size, tol), 3),
        }
        grays.append(gray)
        if not cut_seen:
            for name, variant in variants.items():
                ok, inlier = (True, 1.0) if k == 0 else variant.step(
                    prod_map if name.startswith("prod") else day_map, motion)
                row[name] = {"ok": ok, "inlier": round(inlier, 3),
                             "dev_m": round(probe_distance_m(variant.h, h_ref, size), 2)}
        rows.append(row)
        prev_gray, prev_hist = gray, hist
        print(json.dumps({"m": match, "f": frame_no, **row}, ensure_ascii=False), flush=True)

    # Geri-ileri kapanma: aynı zinciri ters yürüyüp başlangıca dönünce kalan fark
    h_back = h_ref
    for i in range(len(motions) - 1, -1, -1):
        back, _, _ = flow_step(grays[i + 1], grays[i])
        h_back = h_back @ np.linalg.inv(back if back is not None else np.linalg.inv(motions[i]))
    poses = {"static": h_start, "reference": h_ref, **{name: v.h for name, v in variants.items()}}
    return {"match": match, "frame": frame_no, "rows": rows, "size": size, "end_k": len(motions),
            "end_poses": {name: pose.tolist() for name, pose in poses.items()},
            "closure_m": round(probe_distance_m(h_back, h_start, size), 2)}


def summarize(clips: list[dict]) -> dict:
    # k=0 çapanın kendisidir, takip karesi değildir
    rows = [r for c in clips for r in c["rows"] if r["k"] > 0]
    uncut = [r for r in rows if not r["cut"]]
    out: dict = {
        "clips": len(clips), "frames": len(rows), "cut_frames": len(rows) - len(uncut),
        "uncut_frames": len(uncut), "uncut_not_main": sum(not r["main"] for r in uncut),
        "closure_m": sorted(c["closure_m"] for c in clips),
        "reference_inlier_median": {
            "production": float(np.median([r["ref_inlier_prod"] for r in uncut])),
            "daylight": float(np.median([r["ref_inlier_day"] for r in uncut])),
        },
        "reference_pass_085": {
            "production": sum(r["ref_inlier_prod"] >= GATE for r in uncut),
            "daylight": sum(r["ref_inlier_day"] >= GATE for r in uncut),
        },
        "variants": {},
    }
    for name in VARIANTS:
        losses: Counter = Counter()
        ref_key = "ref_inlier_prod" if name.startswith("prod") else "ref_inlier_day"
        gate = LOW_GATE if name.endswith("070") else GATE
        for r in rows:
            produced = not r["cut"] and r[name]["ok"]
            losses[classify_loss(cut=r["cut"], reference_inlier=r[ref_key], produced=produced, gate=gate)] += 1
        kept = [r[name]["dev_m"] for r in uncut if r[name]["ok"]]
        out["variants"][name] = {
            "losses": dict(losses),
            "deviation_from_reference_m": {
                "median": round(float(np.median(kept)), 2) if kept else None,
                "worst": round(float(np.max(kept)), 2) if kept else None,
                "over_5m": sum(d > 5.0 for d in kept),
            },
        }
    return out


def end_grids(folder: Path, out: Path) -> int:
    """El işareti için her klibin son kesintisiz karesi. Duruş bilgisi yazılmaz."""
    import cv2

    from scripts.calibration_funnel import draw_grid
    from scripts.shot_exam import STEP_S

    out.mkdir(parents=True, exist_ok=True)
    for path in sorted(folder.glob("tracking_*.json")):
        for clip in json.loads(path.read_text(encoding="utf-8")):
            frames = list(clip_frames(video_of(clip["match"]), clip["frame"] * STEP_S))
            cv2.imwrite(str(out / f"{clip['match']}_{clip['frame']}.jpg"), draw_grid(frames[clip["end_k"]]),
                        [cv2.IMWRITE_JPEG_QUALITY, 85])
    return 0


def mark_errors(pose: np.ndarray, points: list[dict]) -> np.ndarray:
    """El noktalarının görüntü konumu bu duruşla sahaya düşürülünce kendi saha konumundan farkı (m)."""
    image = np.array([[*p["image"], 1.0] for p in points])
    pitch = np.array([p["pitch"] for p in points], dtype=float)
    mapped = image @ pose.T
    return np.hypot(*(mapped[:, :2] / mapped[:, 2:3] - pitch).T)


def end_errors(clip: dict, points: list[dict]) -> dict[str, dict]:
    """Uç karede her duruşun işaretli noktalardaki hatası; kare o duruşla üretildi mi?"""
    last = clip["rows"][clip["end_k"]]
    return {name: {"median_m": round(float(np.median(mark_errors(np.array(pose), points))), 2),
                   "worst_m": round(float(mark_errors(np.array(pose), points).max()), 2),
                   "produced": bool(last[name]["ok"]) if name in last else None}
            for name, pose in clip["end_poses"].items()}


def truth(folder: Path, marks_path: Path) -> int:
    marks = json.loads(marks_path.read_text(encoding="utf-8"))["frames"]
    per_clip, totals = [], {}
    for path in sorted(folder.glob("tracking_*.json")):
        for clip in json.loads(path.read_text(encoding="utf-8")):
            points = marks.get(clip["match"], {}).get(str(clip["frame"]), {}).get("points")
            if not points or clip["end_k"] == 0:
                continue
            errors = end_errors(clip, points)
            per_clip.append({"match": clip["match"], "frame": clip["frame"],
                             **{k: f"{v['median_m']}/{v['worst_m']}{'*' if v['produced'] else ''}"
                                for k, v in errors.items()}})
            for name, value in errors.items():
                if value["produced"] is not False:
                    totals.setdefault(name, []).append(value["median_m"])
    print(json.dumps({"clips": per_clip,
                      "produced_end_frames": {k: len(v) for k, v in totals.items()},
                      "median_of_medians_m": {k: round(float(np.median(v)), 2) for k, v in totals.items()},
                      "worst_median_m": {k: max(v) for k, v in totals.items()}}, ensure_ascii=False, indent=1))
    return 0


def run(points_path: Path, match: str, out: Path) -> int:
    if MATCH_GROUP.get(match) != "development":
        print(f"{match}: yalnız geliştirme maçları koşulur", file=sys.stderr)
        return 2
    out.mkdir(parents=True, exist_ok=True)
    spec = json.loads(points_path.read_text(encoding="utf-8"))
    clips = [run_clip(match, int(f), v["points"]) for f, v in spec["frames"][match].items() if v.get("points")]
    (out / f"tracking_{match}.json").write_text(json.dumps(clips, ensure_ascii=False), encoding="utf-8")
    return 0


def summary(folder: Path) -> int:
    clips = [c for p in sorted(folder.glob("tracking_*.json")) for c in json.loads(p.read_text(encoding="utf-8"))]
    print(json.dumps(summarize(clips), ensure_ascii=False, indent=1))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--points", type=Path, required=True)
    r.add_argument("--match", required=True)
    r.add_argument("--out", type=Path, required=True)
    s = sub.add_parser("summary")
    s.add_argument("--dir", type=Path, required=True)
    g = sub.add_parser("end-grids")
    g.add_argument("--dir", type=Path, required=True)
    g.add_argument("--out", type=Path, required=True)
    t = sub.add_parser("truth")
    t.add_argument("--dir", type=Path, required=True)
    t.add_argument("--marks", type=Path, required=True)
    args = parser.parse_args()
    if args.cmd == "run":
        return run(args.points, args.match, args.out)
    if args.cmd == "end-grids":
        return end_grids(args.dir, args.out)
    if args.cmd == "truth":
        return truth(args.dir, args.marks)
    return summary(args.dir)


if __name__ == "__main__":
    sys.exit(main())
