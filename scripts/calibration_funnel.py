"""Gündüz yayınında kalibrasyon kaybını aşamalara böler (venv-cv). Üretim koduna dokunmaz.

Ölçüm: docs/measurements/daylight-calibration-funnel.json. Görüntüler repoda değildir.

    venv-cv\\Scripts\\python.exe -X utf8 -m scripts.calibration_funnel funnel --match gamba_kashiwa --out <klasör>
    venv-cv\\Scripts\\python.exe -X utf8 -m scripts.calibration_funnel summary --dir <klasör>
    venv-cv\\Scripts\\python.exe -X utf8 -m scripts.calibration_funnel pick --per-match 6
    venv-cv\\Scripts\\python.exe -X utf8 -m scripts.calibration_funnel grid --match gamba_kashiwa --frame 30 --out k.jpg
    venv-cv\\Scripts\\python.exe -X utf8 -m scripts.calibration_funnel truth \\
        --points docs/measurements/daylight-calibration-truth-points.json --out <klasör>
    venv-cv\\Scripts\\python.exe -X utf8 -m scripts.calibration_funnel candidate \\
        --points docs/measurements/daylight-calibration-truth-points.json

`funnel` kare başına kayıt yazar, `summary` toplar. `pick` elle gerçek duruş işaretlenecek
kareleri yalnız etiket dizisinden seçer, görüntüye bakmaz. `truth` işaretli karelerde üç
karşı-durum koşar: gerçek duruşta kapılar, kusursuz çizgiyle arama, gerçek duruştan takip.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import types
from collections import Counter
from pathlib import Path

import numpy as np

CANDIDATE_COMMIT = "34c98e3dd6e6273ca7a5ba1a4b34edce4a2afc35"

LABEL_FILES = {
    "development": Path("docs/measurements/shot-exam-labels-development.json"),
    "seen_control": Path("docs/measurements/shot-exam-labels-control.json"),
}
MATCH_GROUP = {
    "gamba_kashiwa": "development", "kashima_marinos": "development", "kyoto_kobe": "development",
    "verdy_kashima": "seen_control", "niigata_kashiwa": "seen_control",
}
PLAN_GROUP = {"development": "development", "seen_control": "control"}
PLAN = Path("docs/measurements/shot-exam-plan.json")
MIN_LANDMARK_NOTE = "kadrajda ayırt edici yapı yok"
# find_anchor kapıları sırayla çalışır; ilk düşülen kapı notun başından okunur.
ANCHOR_NOTES = (
    ("kadrajda çizgi pikseli yok", "no_line_pixels"),
    ("hiçbir aday", "no_candidate_visible"),
    (MIN_LANDMARK_NOTE, "landmark_not_visible"),
    ("ayırt edici yapılar oturmadı", "landmark_inlier"),
    ("çapa oturması zayıf", "inlier"),
    ("sahne belirsiz", "margin"),
    ("kadrajdaki çizgilerin", "coverage"),
    ("TV kuralı ile kabul", "accepted"),
)
GATE_ORDER = ("no_line_pixels", "no_candidate_visible", "landmark_not_visible", "landmark_inlier",
              "inlier", "margin", "coverage", "accepted")
# Üretimdeki tolerans: DEFAULT_TOLERANCE_PX × genişlik / 1280
PROD_TOLERANCE_SCALE = 1280.0
TRACK_SECONDS = 3.0
TRACK_FPS = 15.0
# Gerçek duruşun tuttuğunu kabul etmek için en az kaç el noktası
MIN_TRUTH_POINTS = 4


def classify_anchor_note(note: str) -> str:
    """find_anchor notundan ilk düşülen kapının adı."""
    for prefix, name in ANCHOR_NOTES:
        if note.startswith(prefix):
            return name
    return "other"


def video_of(match: str) -> Path:
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    return Path(plan["matches"][PLAN_GROUP[MATCH_GROUP[match]]][match]["file"])


def other_frames(match: str) -> set[int]:
    labels = json.loads(LABEL_FILES[MATCH_GROUP[match]].read_text(encoding="utf-8"))
    return set(labels[match]["other"])


def pick_frames(n_samples: int, others: set[int], per_match: int) -> list[int]:
    """Ana kamera etiketli örneklerden eşit aralıklı `per_match` kare (görüntüsüz seçim)."""
    mains = [i for i in range(n_samples) if i not in others]
    if len(mains) <= per_match:
        return mains
    return [mains[int((k + 0.5) * len(mains) / per_match)] for k in range(per_match)]


def tolerance_for(width: int) -> float:
    from app.tracking.homography_fit import DEFAULT_TOLERANCE_PX

    return DEFAULT_TOLERANCE_PX * (width / PROD_TOLERANCE_SCALE)


def funnel_record(frame: np.ndarray) -> dict:
    """Bir kare için üretim çıkarıcısı + find_anchor; her kapı ayrıca ölçülür."""
    from app.tracking.homography_fit import (
        find_anchor,
        line_coverage,
        model_points,
        score_homography,
    )
    from app.tracking.pitch_lines import MIN_LINE_PIXELS, extract_lines

    h, w = frame.shape[:2]
    tol = tolerance_for(w)
    ext = extract_lines(frame)
    rec: dict = {"grass_ratio": round(ext.grass_ratio, 3), "line_pixels": ext.line_pixels,
                 "line_gate": ext.line_pixels >= MIN_LINE_PIXELS}
    if not rec["line_gate"]:
        return rec
    res = find_anchor(ext.dist_map, (w, h), tolerance_px=tol, assume_camera_side=True)
    rec["first_failed_gate"] = classify_anchor_note(res.note)
    if res.fit is not None:
        lm_pts = model_points(1.0, "landmark")
        _, lm_inlier, lm_visible = score_homography(res.fit.homography, ext.dist_map, pts_m=lm_pts, tolerance_px=tol)
        rec.update(
            best_inlier=round(res.fit.inlier_ratio, 3), best_visible=res.fit.visible_points,
            lm_inlier=round(lm_inlier, 3), lm_visible=lm_visible,
            coverage=round(line_coverage(res.fit.homography, ext.dist_map <= 0.5, tolerance_px=2.0 * tol), 3),
        )
    return rec


def funnel(match: str, out: Path) -> int:
    from scripts.shot_exam import sampled_frames

    out.mkdir(parents=True, exist_ok=True)
    others = other_frames(match)
    rows = []
    for i, frame in sampled_frames(video_of(match)):
        rows.append({"match": match, "group": MATCH_GROUP[match], "frame": i,
                     "label": "other" if i in others else "main", **funnel_record(frame)})
    (out / f"{match}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"{match}: {len(rows)} kare")
    return 0


def summarize(rows: list[dict]) -> dict:
    """Etiket başına huni: çizgi kapısı → find_anchor ilk düşülen kapı → kabul."""
    out: dict = {}
    for label in ("main", "other"):
        sel = [r for r in rows if r["label"] == label]
        lined = [r for r in sel if r["line_gate"]]
        gates = Counter(r["first_failed_gate"] for r in lined)
        with_fit = [r for r in lined if "best_inlier" in r]
        out[label] = {
            "frames": len(sel),
            "grass_ratio_median": round(float(np.median([r["grass_ratio"] for r in sel])), 3) if sel else None,
            "line_pixels_median": int(np.median([r["line_pixels"] for r in sel])) if sel else None,
            "pass_line_gate": len(lined),
            "first_failed_gate": {g: gates[g] for g in GATE_ORDER if gates[g]},
            "independent_pass": {
                "landmark_visible_ge25": sum(r["lm_visible"] >= 25 for r in with_fit),
                "landmark_inlier_ge070": sum(r["lm_inlier"] >= 0.70 for r in with_fit),
                "inlier_ge090": sum(r["best_inlier"] >= 0.90 for r in with_fit),
                "coverage_ge060": sum(r["coverage"] >= 0.60 for r in with_fit),
            },
            "accepted": gates["accepted"],
        }
    return out


def summary(folder: Path) -> int:
    rows: list[dict] = []
    per: dict = {}
    for path in sorted(folder.glob("*.json")):
        if path.name.startswith("truth"):
            continue
        part = json.loads(path.read_text(encoding="utf-8"))
        per[path.stem] = summarize(part)
        rows += part
    print(json.dumps({"per_match": per, "total": summarize(rows)}, ensure_ascii=False, indent=1))
    return 0


def pick(per_match: int) -> int:
    for match in MATCH_GROUP:
        if MATCH_GROUP[match] == "development":
            print(match, pick_frames(120, other_frames(match), per_match))
    return 0


def grid(match: str, frame_no: int, out: Path) -> int:
    """El işareti için kare: 100 px ızgara, koordinat yazılı (görüntü repoya girmez)."""
    import cv2

    from scripts.shot_exam import sampled_frames

    for i, frame in sampled_frames(video_of(match)):
        if i != frame_no:
            continue
        canvas = frame.copy()
        for x in range(0, canvas.shape[1], 100):
            cv2.line(canvas, (x, 0), (x, canvas.shape[0]), (0, 255, 255) if x % 500 == 0 else (0, 200, 200), 1)
            cv2.putText(canvas, str(x), (x + 2, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1)
        for y in range(0, canvas.shape[0], 100):
            cv2.line(canvas, (0, y), (canvas.shape[1], y), (0, 255, 255) if y % 500 == 0 else (0, 200, 200), 1)
            cv2.putText(canvas, str(y), (2, y + 14), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1)
        cv2.imwrite(str(out), canvas, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return 0
    raise SystemExit("kare bulunamadı")


def homography_from_points(points: list[dict]) -> np.ndarray:
    """El noktalarından görüntü → saha homografisi (en küçük kareler DLT)."""
    from app.tracking.homography_fit import dlt_homography

    if len(points) < MIN_TRUTH_POINTS:
        raise ValueError(f"{MIN_TRUTH_POINTS} nokta gerekir")
    return dlt_homography(np.array([p["image"] for p in points], float), np.array([p["pitch"] for p in points], float))


def miss_causes(frame: np.ndarray, h_truth: np.ndarray, tol: float) -> dict:
    """Gerçek duruşta kadraja düşen model noktaları neden çizgi maskesinde yok?"""
    import cv2

    from app.tracking.homography_fit import model_points, project_to_image
    from app.tracking.pitch_lines import (
        GRASS_HSV_HIGH,
        GRASS_HSV_LOW,
        LINE_THICKNESS_PX,
        WHITE_MIN_VALUE,
        extract_lines,
    )

    h_img, w_img = frame.shape[:2]
    uv = project_to_image(h_truth, model_points(1.0))
    uv = uv[np.isfinite(uv).all(axis=1)]
    uv = uv[(uv[:, 0] >= 0) & (uv[:, 0] < w_img) & (uv[:, 1] >= 0) & (uv[:, 1] < h_img)].astype(int)
    ext = extract_lines(frame)
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    grass = cv2.inRange(hsv, np.array(GRASS_HSV_LOW), np.array(GRASS_HSV_HIGH))
    region = cv2.morphologyEx(grass, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (25, 25)))
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (LINE_THICKNESS_PX, LINE_THICKNESS_PX))
    thin = cv2.subtract(gray, cv2.morphologyEx(gray, cv2.MORPH_OPEN, k))
    otsu, _ = cv2.threshold(thin, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # Noktanın tolerans içindeki en parlak ince yapı pikseli: el duruşu birkaç px kayık olabilir.
    r = int(round(tol))
    grown_gray = cv2.dilate(gray, np.ones((2 * r + 1, 2 * r + 1), np.uint8))
    grown_thin = cv2.dilate(thin, np.ones((2 * r + 1, 2 * r + 1), np.uint8))
    grown_region = cv2.dilate(region, np.ones((2 * r + 1, 2 * r + 1), np.uint8))
    causes: Counter = Counter()
    for u, v in uv:
        if ext.dist_map[v, u] <= tol:
            causes["hit"] += 1
        elif grown_region[v, u] == 0:
            causes["outside_pitch_mask"] += 1
        elif grown_gray[v, u] < WHITE_MIN_VALUE:
            causes["below_white_floor_140"] += 1
        elif grown_thin[v, u] < otsu:
            causes["below_otsu"] += 1
        else:
            causes["both_pass_apart"] += 1
    return {"model_points_in_frame": len(uv), **causes, "otsu": float(otsu)}


def ideal_dist_map(h_truth: np.ndarray, size: tuple[int, int]) -> tuple[np.ndarray, int]:
    """Gerçek duruştan çizilmiş kusursuz çizgi haritası: arama tek başına çalışır mı?"""
    import cv2

    from app.tracking.homography_fit import model_points, project_to_image

    w, h = size
    uv = project_to_image(h_truth, model_points(0.1))
    uv = uv[np.isfinite(uv).all(axis=1)]
    uv = uv[(uv[:, 0] >= 0) & (uv[:, 0] < w) & (uv[:, 1] >= 0) & (uv[:, 1] < h)].astype(int)
    mask = np.zeros((h, w), np.uint8)
    mask[uv[:, 1], uv[:, 0]] = 255
    mask = cv2.dilate(mask, np.ones((3, 3), np.uint8)) > 0
    return cv2.distanceTransform((~mask).astype(np.uint8), cv2.DIST_L2, 3), int(mask.sum())


def probe_distance_m(h_a: np.ndarray, h_b: np.ndarray, size: tuple[int, int]) -> float:
    """İki homografinin görüntü merkezindeki ızgarada en büyük saha farkı (m)."""
    w, h = size
    pts = np.array([[w * fx, h * fy, 1.0] for fx in (0.25, 0.5, 0.75) for fy in (0.45, 0.6, 0.75)])
    a, b = pts @ h_a.T, pts @ h_b.T
    return float(np.hypot(*((a[:, :2] / a[:, 2:3]) - (b[:, :2] / b[:, 2:3])).T).max())


def refined_pose(frame: np.ndarray, h_hand: np.ndarray) -> np.ndarray:
    """El duruşunu üretim çizgilerine yerel oturt; 3 m'den fazla kayarsa el duruşu kalır."""
    from app.tracking.homography_fit import refine_homography
    from app.tracking.pitch_lines import extract_lines

    h, w = frame.shape[:2]
    fit = refine_homography(h_hand, extract_lines(frame).dist_map, tolerance_px=tolerance_for(w), step_px=4.0)
    return fit.homography if probe_distance_m(fit.homography, h_hand, (w, h)) < 3.0 else h_hand


def truth_record(match: str, frame_no: int, frame: np.ndarray, h_truth: np.ndarray) -> dict:
    from app.tracking.homography_fit import (
        anchor_candidates,
        find_anchor,
        line_coverage,
        model_points,
        score_homography,
    )
    from app.tracking.pitch_lines import extract_lines

    h, w = frame.shape[:2]
    tol = tolerance_for(w)
    ext = extract_lines(frame)
    lm_pts = model_points(1.0, "landmark")
    pose = refined_pose(frame, h_truth)
    _, inl, vis = score_homography(pose, ext.dist_map, pts_m=model_points(1.0), tolerance_px=tol)
    _, lm_inl, lm_vis = score_homography(pose, ext.dist_map, pts_m=lm_pts, tolerance_px=tol)
    cov = line_coverage(pose, ext.dist_map <= 0.5, tolerance_px=2.0 * tol)

    real = find_anchor(ext.dist_map, (w, h), tolerance_px=tol, assume_camera_side=True)
    ideal_map, ideal_px = ideal_dist_map(pose, (w, h))
    ideal = find_anchor(ideal_map, (w, h), tolerance_px=tol, assume_camera_side=True)
    cands = anchor_candidates((w, h))
    nearest = min(probe_distance_m(c, pose, (w, h)) for c in cands)
    return {
        "match": match, "frame": frame_no,
        "gates_at_truth": {
            "inlier": round(inl, 3), "visible": vis, "landmark_inlier": round(lm_inl, 3),
            "landmark_visible": lm_vis, "coverage": round(cov, 3),
            "pass_anchor_gates": bool(lm_vis >= 25 and lm_inl >= 0.70 and inl >= 0.90 and cov >= 0.60),
            "pass_track_085": bool(inl >= 0.85),
        },
        "refine_moved_m": round(probe_distance_m(pose, h_truth, (w, h)), 2),
        "miss_causes": miss_causes(frame, pose, tol),
        "real_lines_search": {
            "gate": classify_anchor_note(real.note),
            "best_error_m": round(probe_distance_m(real.fit.homography, pose, (w, h)), 1) if real.fit else None,
            "best_inlier": round(real.fit.inlier_ratio, 3) if real.fit else None,
        },
        "ideal_lines_search": {
            "ideal_line_px": ideal_px,
            "gate": classify_anchor_note(ideal.note),
            "best_error_m": round(probe_distance_m(ideal.fit.homography, pose, (w, h)), 1) if ideal.fit else None,
            "best_inlier": round(ideal.fit.inlier_ratio, 3) if ideal.fit else None,
        },
        "nearest_candidate_m": round(nearest, 1),
        "tracking_from_truth": track_from_truth(match, frame_no, pose, (w, h)),
    }


def track_from_truth(match: str, frame_no: int, pose: np.ndarray, size: tuple[int, int]) -> dict:
    """Gerçek duruşu üretim kalibratörüne çapa ver, sonraki TRACK_SECONDS saniyeyi say."""
    import cv2

    from app.tracking.pitch_lines import PerFrameCalibrator, calibration_from_homography
    from scripts.shot_exam import STEP_S

    cal = PerFrameCalibrator(calibration_from_homography(pose, size), allow_reacquire=True)
    cap = cv2.VideoCapture(str(video_of(match)))
    frames = int(TRACK_SECONDS * TRACK_FPS)
    produced, reasons = 0, Counter()
    for k in range(frames):
        cap.set(cv2.CAP_PROP_POS_MSEC, (frame_no * STEP_S + k / TRACK_FPS) * 1000.0)
        ok, frame = cap.read()
        if not ok:
            break
        fc = cal.process(frame)
        if fc.ok:
            produced += 1
        else:
            reasons[fc.reason.split(" ")[0] if fc.reason else "?"] += 1
    cap.release()
    return {"frames": frames, "produced": produced, "miss_reasons": dict(reasons)}


def write_overlay(path: Path, frame: np.ndarray, pose: np.ndarray) -> None:
    """Kontrol görseli: gerçek duruşun model çizgileri (macenta) karenin üstünde."""
    import cv2

    from app.tracking.homography_fit import model_points, project_to_image

    canvas = frame.copy()
    uv = project_to_image(pose, model_points(0.25))
    uv = uv[np.isfinite(uv).all(axis=1)]
    uv = uv[(uv[:, 0] >= 0) & (uv[:, 0] < frame.shape[1]) & (uv[:, 1] >= 0) & (uv[:, 1] < frame.shape[0])].astype(int)
    for u, v in uv[::4]:
        cv2.circle(canvas, (int(u), int(v)), 2, (255, 0, 255), -1)
    cv2.imwrite(str(path), cv2.resize(canvas, (960, 540), interpolation=cv2.INTER_AREA), [cv2.IMWRITE_JPEG_QUALITY, 80])


def truth(points_path: Path, out: Path) -> int:
    from scripts.shot_exam import sampled_frames

    out.mkdir(parents=True, exist_ok=True)
    spec = json.loads(points_path.read_text(encoding="utf-8"))
    rows = []
    for match, frames in spec["frames"].items():
        wanted = {int(k): v for k, v in frames.items() if v.get("points")}
        for i, frame in sampled_frames(video_of(match)):
            if i in wanted:
                h_hand = homography_from_points(wanted[i]["points"])
                write_overlay(out / f"overlay_{match}_{i}.jpg", frame, refined_pose(frame, h_hand))
                rows.append(truth_record(match, i, frame, h_hand))
                print(json.dumps(rows[-1], ensure_ascii=False), flush=True)
    (out / "truth_records.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


def candidate_extractor(commit: str = CANDIDATE_COMMIT):
    """PR #339'dan geri alınan yerel kontrast çıkarıcısı: git'ten okunur, üretime girmez."""
    source = subprocess.run(["git", "show", f"{commit}:app/tracking/pitch_lines.py"],
                            capture_output=True, check=True).stdout.decode("utf-8")
    module = types.ModuleType("candidate_pitch_lines")
    sys.modules[module.__name__] = module
    exec(compile(source, module.__name__, "exec"), module.__dict__)  # noqa: S102
    return module.extract_lines


def candidate(points_path: Path) -> int:
    """Aynı gerçek duruşta üretim ve aday çıkarıcıyı kıyasla (aday kod yalnız burada koşar)."""
    from app.tracking.homography_fit import line_coverage, model_points, score_homography
    from app.tracking.pitch_lines import extract_lines
    from scripts.shot_exam import sampled_frames

    extract = candidate_extractor()
    spec = json.loads(points_path.read_text(encoding="utf-8"))
    for match, frames in spec["frames"].items():
        wanted = {int(k): v for k, v in frames.items() if v.get("points")}
        for i, frame in sampled_frames(video_of(match)):
            if i not in wanted:
                continue
            pose = refined_pose(frame, homography_from_points(wanted[i]["points"]))
            tol = tolerance_for(frame.shape[1])
            row = {"match": match, "frame": i}
            for name, ext in (("production", extract_lines(frame)), ("candidate", extract(frame))):
                _, inl, _ = score_homography(pose, ext.dist_map, pts_m=model_points(1.0), tolerance_px=tol)
                _, lm, _ = score_homography(pose, ext.dist_map, pts_m=model_points(1.0, "landmark"), tolerance_px=tol)
                cov = line_coverage(pose, ext.dist_map <= 0.5, tolerance_px=2.0 * tol)
                # Ayırt edicilik: duruş 8 m kaydırılınca inlier ne kadar düşüyor?
                shifted = np.array([[1.0, 0.0, 8.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]) @ pose
                _, inl_shift, _ = score_homography(shifted, ext.dist_map, pts_m=model_points(1.0), tolerance_px=tol)
                row[name] = {"inlier": round(inl, 3), "landmark_inlier": round(lm, 3),
                             "coverage": round(cov, 3), "line_pixels": ext.line_pixels,
                             "inlier_shifted_8m": round(inl_shift, 3)}
            print(json.dumps(row, ensure_ascii=False), flush=True)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("funnel")
    f.add_argument("--match", required=True, choices=sorted(MATCH_GROUP))
    f.add_argument("--out", required=True)
    s = sub.add_parser("summary")
    s.add_argument("--dir", required=True)
    k = sub.add_parser("pick")
    k.add_argument("--per-match", type=int, default=6)
    g = sub.add_parser("grid")
    g.add_argument("--match", required=True, choices=sorted(MATCH_GROUP))
    g.add_argument("--frame", type=int, required=True)
    g.add_argument("--out", required=True)
    t = sub.add_parser("truth")
    t.add_argument("--points", required=True)
    t.add_argument("--out", required=True)
    c = sub.add_parser("candidate")
    c.add_argument("--points", required=True)
    a = p.parse_args()
    if a.cmd == "candidate":
        return candidate(Path(a.points))
    if a.cmd == "funnel":
        return funnel(a.match, Path(a.out))
    if a.cmd == "summary":
        return summary(Path(a.dir))
    if a.cmd == "pick":
        return pick(a.per_match)
    if a.cmd == "grid":
        return grid(a.match, a.frame, Path(a.out))
    return truth(Path(a.points), Path(a.out))


if __name__ == "__main__":
    raise SystemExit(main())
