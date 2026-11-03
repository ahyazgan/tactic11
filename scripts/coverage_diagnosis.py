"""Çapa+takip kapsamasının maçtan maça neden değiştiğini ölçer (venv-cv). Ürün koduna dokunmaz.

Ölçüm: docs/measurements/broadcast-track-coverage-diagnosis.json. Görüntüler repoda değildir.

    venv-cv\\Scripts\\python.exe -X utf8 -m scripts.coverage_diagnosis run --match kyoto_kobe --arm base --out <klasör>
    venv-cv\\Scripts\\python.exe -X utf8 -m scripts.coverage_diagnosis factors --dir <klasör> --out <json>
    venv-cv\\Scripts\\python.exe -X utf8 -m scripts.coverage_diagnosis summary --factors <json>
    venv-cv\\Scripts\\python.exe -X utf8 -m scripts.coverage_diagnosis flatten --factors <json>
    venv-cv\\Scripts\\python.exe -X utf8 -m scripts.coverage_diagnosis arms --dir <klasör>

`run` kolları: base kodun kendisi; long_block 6 sn taşıma, arama durur (geri alınan tasarım);
long_search 6 sn taşıma, kapı kaçan karede arama sürer; no_filters çekim ayırıcı ve tekrar
izleyici devre dışı. Kollar yalnız bu araçtadır.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import numpy as np

import app.tracking.broadcast_track as bt
from scripts.broadcast_track_exam import FPS, track_video
from scripts.calibration_funnel import MATCH_GROUP, homography_from_points, other_frames, video_of
from scripts.tracking_funnel import mark_errors

CONTROL_PLAN = Path("docs/measurements/broadcast-tracking-preregistration.json")
CONTROL_LABELS = Path("docs/measurements/broadcast-track-labels-control.json")
MARK_FILES = (
    Path("docs/measurements/daylight-calibration-truth-points.json"),
    Path("docs/measurements/broadcast-track-derived-truth-points.json"),
    Path("docs/measurements/broadcast-track-truth-points-control.json"),
)
LONG_COAST_FRAMES = 90
BRIDGE_CLOSURE_M = 3.0
SHADOW_RATIO = 0.7          # çim medyan parlaklığının altı gölge sayılır
FLATTEN_BLUR_PX = 151       # gölge düzleştirme karşı-deneyi: geniş bulanık bölme
REASONS = {
    "searching": "anchor_missing", "no_anchor": "anchor_missing",
    "gate": "line_gate_rejected", "gate_lost": "tracking_lost", "not_main_lost": "tracking_lost",
    "not_main": "shot_filter", "replay": "replay", "cut": "cut",
}
FACTORS = ("grass_ratio", "lines", "mask_px", "shadow_share", "sharpness", "run_length")


def reason_of(state: str) -> str:
    return REASONS.get(state, "posed")


def source(match: str) -> tuple[Path, set[int]]:
    """Video ve other etiketleri: geliştirme, görülmüş veya tüketilmiş kontrol maçı."""
    if match in MATCH_GROUP:
        return video_of(match), other_frames(match)
    plan = json.loads(CONTROL_PLAN.read_text(encoding="utf-8"))
    labels = json.loads(CONTROL_LABELS.read_text(encoding="utf-8"))
    return Path(plan["control_matches"][match]["file"]), set(labels[match]["other"])


def run_lengths(labels: list[str]) -> list[int]:
    """Her örnek için içinde bulunduğu kesintisiz main dizisinin boyu; other için 0."""
    out = [0] * len(labels)
    i = 0
    while i < len(labels):
        j = i
        while j < len(labels) and labels[j] == "main":
            j += 1
        out[i:j] = [j - i] * (j - i)
        i = max(j, i + 1)
    return out


def tercile_rates(values: list[float], posed: list[bool]) -> list[dict]:
    """Etkenin üç diliminde kapsama. Dilim sınırları değerlerin kendisinden gelir."""
    edges = np.quantile(values, [1 / 3, 2 / 3])
    buckets = np.digitize(values, edges, right=True)
    rows = []
    for b in range(3):
        chosen = [p for p, g in zip(posed, buckets, strict=True) if g == b]
        rows.append({"n": len(chosen), "posed": sum(chosen),
                     "rate": round(sum(chosen) / len(chosen), 3) if chosen else None})
    return rows


class ArmForward(bt.BroadcastTracker):
    """Uzun taşıma kolları. `searching` doğruysa kapı kaçan karede çapa ve yeniden konumlanma sürer."""

    def __init__(self, fps: float, *, searching: bool) -> None:
        super().__init__(fps)
        self._searching = searching
        self._frame: np.ndarray | None = None

    def step(self, bgr: np.ndarray) -> bt.TrackFrame:
        self._frame = bgr
        return super().step(bgr)

    def _coasted(self, carried: np.ndarray | None, state: str) -> bt.TrackFrame:
        if carried is None:
            return bt.TrackFrame(None, state)
        self._coast += 1
        if self._coast > LONG_COAST_FRAMES:
            self._drop()
            return bt.TrackFrame(None, f"{state}_lost")
        self._h = carried
        if self._searching and state == "gate":
            assert self._frame is not None and self._prev_gray is not None
            found = self._search(bt.daylight_line_mask(self._frame), self._prev_gray)
            if found.homography is not None:
                return found
        return bt.TrackFrame(None, state, carried=carried, origin=self._origin)


class ArmBackfill(bt.BackfillingTracker):
    """Geri alınan köprü: kesintisiz gate/not_main boşluğu, sonda akış çizgiyle ≤3 m kapanırsa üretilir."""

    def __init__(self, fps: float, *, searching: bool) -> None:
        super().__init__(fps)
        self._forward = ArmForward(fps, searching=searching)
        self.closure = {"m": 0.0}
        original = bt.corrected_pose

        def recording(carried: np.ndarray, mask: np.ndarray) -> tuple[np.ndarray, float] | None:
            fit = original(carried, mask)
            if fit is not None:
                self.closure["m"] = bt.pose_shift_m(fit[0], carried, (mask.shape[1], mask.shape[0]))
            return fit

        bt.corrected_pose = recording

    def feed(self, k: int, bgr: np.ndarray) -> list[tuple[int, bt.TrackFrame]]:
        import cv2

        result = self._forward.step(bgr)
        out = [(k, result)]
        if result.state in {"gate", "not_main"} and result.carried is not None:
            self._gap.append((k, result.carried))
        else:
            if result.state == "tracked" and self.closure["m"] <= BRIDGE_CLOSURE_M:
                out += [(g, bt.TrackFrame(p, "bridged", origin=result.origin)) for g, p in self._gap]
            self._gap = []
        if result.state in {"anchored", "relocalized"} and result.homography is not None:
            out += self._walk_back(result.homography, bgr, result.origin)
        if result.state == "cut" or result.state not in bt.BUFFERED_STATES:
            self._buffer.clear()
        if result.state in bt.BUFFERED_STATES:
            ok, encoded = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, bt.BUFFER_JPEG_QUALITY])
            if ok:
                self._buffer.append((k, encoded))
        return out


def run(match: str, arm: str, out: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    if arm == "no_filters":
        bt.classify_shot = lambda _f: SimpleNamespace(is_main=True)  # type: ignore[assignment, return-value]
        bt.red_ratio = lambda _f: 0.0
    elif arm != "base":
        searching = arm == "long_search"
        bt.BackfillingTracker = lambda fps=FPS: ArmBackfill(fps, searching=searching)  # type: ignore[misc, assignment]
    video, others = source(match)
    record = track_video(match, video, others, set())
    record["arm"] = arm
    (out / f"{match}__{arm}.json").write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    return 0


def arm_counts(samples: list[dict]) -> dict:
    """Bir kolun main kapsaması, kayıp nedenleri ve other sızıntısı."""
    main = [s for s in samples if s["label"] == "main"]
    other = [s for s in samples if s["label"] == "other"]
    return {"main_posed": sum(s["posed"] for s in main), "main_n": len(main),
            "other_posed": sum(s["posed"] for s in other), "other_n": len(other),
            "lost": dict(Counter(reason_of(s["state"]) for s in main if not s["posed"]))}


def arms(folder: Path) -> int:
    """Kol başına sayımlar ve işaretli main örneklerinde kare medyan hatası."""
    report: dict[str, dict] = {}
    for path in sorted(folder.glob("*__*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        match, arm = record["match"], record["arm"]
        marks = marked_samples(match)
        errors = [round(float(np.median(mark_errors(np.array(s["pose"]), marks[s["sample"]]))), 2)
                  for s in record["samples"] if s["label"] == "main" and s["posed"] and s["sample"] in marks]
        report.setdefault(arm, {})[match] = {**arm_counts(record["samples"]), "marked_errors_m": sorted(errors)}
    json.dump(report, sys.stdout, ensure_ascii=False)
    return 0


def marked_samples(match: str) -> dict[int, list[dict]]:
    marks: dict[int, list[dict]] = {}
    for path in MARK_FILES:
        frames = json.loads(path.read_text(encoding="utf-8"))["frames"].get(match, {})
        for sample, spec in frames.items():
            if len(spec.get("points", [])) >= 4:
                marks[int(sample)] = spec["points"]
    return marks


def view_metrics(points: list[dict], size: tuple[int, int]) -> dict | None:
    """El duruşundan kadraj: görüntü genişliğinin saha karşılığı ve görünen ayırt edici yapı noktası."""
    from app.tracking.homography_fit import model_points, score_homography

    pose = homography_from_points(points)
    w, h = size
    row = np.array([[0.25 * w, 0.6 * h, 1.0], [0.75 * w, 0.6 * h, 1.0]]) @ pose.T
    if np.any(np.abs(row[:, 2]) < 1e-9):
        return None
    xy = row[:, :2] / row[:, 2:3]
    visible = score_homography(pose, np.zeros((h, w), np.float32), pts_m=model_points(1.0, "landmark"),
                               tolerance_px=9.0)[2]
    return {"view_width_m": round(float(np.hypot(*(xy[1] - xy[0])) * 2.0), 1), "landmarks": int(visible)}


def frame_factors(frame: np.ndarray) -> dict:
    import cv2

    from app.tracking.broadcast_anchor import (
        RIDGE_MIN_SHARE,
        daylight_line_mask,
        detect_lines,
        ridge_share,
    )
    from app.tracking.shot_filter import classify_shot

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    grass = cv2.inRange(hsv, np.array((28, 25, 18)), np.array((95, 255, 255))) > 0
    value = cv2.blur(hsv[:, :, 2], (31, 31))
    shadow = 0.0
    if grass.any():
        shadow = float((value[grass] < SHADOW_RATIO * np.median(value[grass])).mean())
    mask = daylight_line_mask(frame)
    lines = [ln for ln in detect_lines(mask) if ridge_share(gray, ln) >= RIDGE_MIN_SHARE]
    verdict = classify_shot(frame)
    return {"grass_ratio": round(verdict.features.grass_ratio, 3), "shot_reason": verdict.reason, "lines": len(lines),
            "mask_px": int(mask.sum()), "shadow_share": round(shadow, 3),
            "sharpness": round(float(cv2.Laplacian(gray, cv2.CV_64F).var()), 1)}


def probe_lost(frame: np.ndarray, gray: np.ndarray, reloc: bt.Relocalizer) -> dict:
    """Çapa bekleyen örnekte tek kare çapa neden reddetti, geçmiş anahtarlarla yeniden konumlanma ne yaptı?"""
    from app.tracking.broadcast_anchor import find_broadcast_anchor

    mask = bt.daylight_line_mask(frame)
    note = find_broadcast_anchor(mask, gray).note.split(" (")[0]
    located = reloc.locate(gray)
    outcome = "no_match" if located is None else ("passes" if bt.corrected_pose(located, mask) is not None else "gate")
    return {"anchor_note": note, "reloc": outcome}


def factors(folder: Path, out: Path) -> int:
    import cv2

    from scripts.shot_exam import sampled_frames

    rows = []
    for path in sorted(folder.glob("*__base.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        match = record["match"]
        video, _ = source(match)
        marks = marked_samples(match)
        lengths = run_lengths([s["label"] for s in record["samples"]])
        by_sample = {s["sample"]: (s, n) for s, n in zip(record["samples"], lengths, strict=True)}
        reloc = bt.Relocalizer()
        for i, frame in sampled_frames(video):
            if i not in by_sample or by_sample[i][0]["label"] != "main":
                continue
            s, length = by_sample[i]
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            row = {"match": match, "sample": i, "state": s["state"], "reason": reason_of(s["state"]),
                   "posed": s["posed"], "origin": s.get("origin"), "run_length": length, **frame_factors(frame)}
            if i in marks:
                row.update(view_metrics(marks[i], (frame.shape[1], frame.shape[0])) or {})
            if row["reason"] == "anchor_missing":
                row.update(probe_lost(frame, gray, reloc))
            if s["posed"] and s.get("origin") == "anchor":
                reloc.add(gray, np.array(s["pose"]))
            rows.append(row)
        print(match, sum(r["match"] == match for r in rows), flush=True)
    out.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    return 0


def summary(factors_path: Path) -> int:
    rows = json.loads(factors_path.read_text(encoding="utf-8"))
    matches = sorted({r["match"] for r in rows})
    table = {}
    for match in matches:
        part = [r for r in rows if r["match"] == match]
        lost = [r for r in part if not r["posed"]]
        waiting = [r for r in lost if r["reason"] == "anchor_missing"]
        table[match] = {
            "main": len(part), "posed": len(part) - len(lost),
            "rate": round(1 - len(lost) / len(part), 3),
            "reasons": dict(Counter(r["reason"] for r in lost)),
            "anchor_notes": dict(Counter(r["anchor_note"] for r in waiting)),
            "reloc_outcomes": dict(Counter(r["reloc"] for r in waiting)),
            "shot_reasons": dict(Counter(r["shot_reason"] for r in lost if r["reason"] == "shot_filter")),
            "medians": {f: float(np.median([r[f] for r in part])) for f in FACTORS},
        }
    report: dict = {"per_match": table, "factor_terciles_pooled": {}, "within_match_posed_minus_lost": {}, "marked_view": {}}
    posed = [r["posed"] for r in rows]
    for f in FACTORS:
        report["factor_terciles_pooled"][f] = tercile_rates([r[f] for r in rows], posed)
        diffs = {}
        for match in matches:
            a = [r[f] for r in rows if r["match"] == match and r["posed"]]
            b = [r[f] for r in rows if r["match"] == match and not r["posed"]]
            if a and b:
                diffs[match] = round(float(np.median(a) - np.median(b)), 3)
        report["within_match_posed_minus_lost"][f] = diffs
    reached = [r for r in rows if r["reason"] in {"posed", "anchor_missing", "line_gate_rejected", "tracking_lost"}]
    report["past_shot_filters_mask_px_terciles"] = tercile_rates([r["mask_px"] for r in reached],
                                                                 [r["posed"] for r in reached])
    report["past_shot_filters_sharpness_terciles"] = tercile_rates([r["sharpness"] for r in reached],
                                                                   [r["posed"] for r in reached])
    marked = [r for r in rows if "view_width_m" in r]
    for f in ("view_width_m", "landmarks"):
        report["marked_view"][f] = {
            "n": len(marked), "terciles": tercile_rates([r[f] for r in marked], [r["posed"] for r in marked]),
            "per_match_median": {m: float(np.median([r[f] for r in marked if r["match"] == m]))
                                 for m in matches if any(r["match"] == m for r in marked)},
        }
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


def flattened(frame: np.ndarray) -> np.ndarray:
    """Gölge karşı-deneyi: parlaklık kanalını geniş bulanık kopyasına böler, renk kalır."""
    import cv2

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV).astype(np.float32)
    value = hsv[:, :, 2]
    base = cv2.blur(value, (FLATTEN_BLUR_PX, FLATTEN_BLUR_PX))
    hsv[:, :, 2] = np.clip(value / np.maximum(base, 1.0) * float(np.median(value)), 0, 255)
    return cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)


def flatten(factors_path: Path) -> int:
    """Çapa bekleyen ve duruşlu örneklerde tek kare çapa: özgün kare ile gölgesi düzleştirilmiş kare."""
    import cv2

    from app.tracking.broadcast_anchor import find_broadcast_anchor
    from scripts.shot_exam import sampled_frames

    rows = json.loads(factors_path.read_text(encoding="utf-8"))
    result = {}
    for match in sorted({r["match"] for r in rows}):
        wanted = {r["sample"]: r for r in rows if r["match"] == match}
        counts: Counter = Counter()
        marks = marked_samples(match)
        errors: dict[str, list[float]] = {"original": [], "flattened": []}
        for i, frame in sampled_frames(source(match)[0]):
            if i not in wanted:
                continue
            shaded = "shadow" if wanted[i]["shadow_share"] >= 0.05 else "flat"
            for name, image in (("original", frame), ("flattened", flattened(frame))):
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
                res = find_broadcast_anchor(bt.daylight_line_mask(image), gray)
                counts[f"{shaded}_{name}"] += res.accepted
                if res.accepted and res.homography is not None and i in marks:
                    errors[name].append(round(float(np.median(mark_errors(res.homography, marks[i]))), 2))
            counts[f"{shaded}_n"] += 1
        result[match] = {**counts, "marked_errors_m": errors}
        print(match, result[match], flush=True)
    print(json.dumps(result, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--match", required=True)
    r.add_argument("--arm", choices=("base", "long_block", "long_search", "no_filters"), required=True)
    r.add_argument("--out", type=Path, required=True)
    f = sub.add_parser("factors")
    f.add_argument("--dir", type=Path, required=True)
    f.add_argument("--out", type=Path, required=True)
    for name in ("summary", "flatten"):
        c = sub.add_parser(name)
        c.add_argument("--factors", type=Path, required=True)
    a = sub.add_parser("arms")
    a.add_argument("--dir", type=Path, required=True)
    args = parser.parse_args()
    if args.cmd == "run":
        return run(args.match, args.arm, args.out)
    if args.cmd == "factors":
        return factors(args.dir, args.out)
    if args.cmd == "summary":
        return summary(args.factors)
    if args.cmd == "arms":
        return arms(args.dir)
    return flatten(args.factors)


if __name__ == "__main__":
    sys.exit(main())
