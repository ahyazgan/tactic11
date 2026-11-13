"""Maç raporu — takip karelerinden dilim dilim takım şekli ve pres, tek yanıtta.

`compute_team_shape` ve `compute_pressure` her dilime ayrı uygulanır; maç özeti
güvenilir dilimlerin kare ağırlıklı ortalamasıdır. Bir dilim, ortalamadan
`tracking_signals` eşikleri kadar saparsa "bulgu" olarak işaretlenir.

Sınırlar (yanıtta `limits` olarak da döner):
  - Saha yönü bilinmez: `centroid_x` ham saha yüzdesidir, "blok yüksekliği" değildir.
  - Takım ayrımı renge dayanır; yanlış takıma düşen oyuncu genişlik ve derinliği büyütür.
  - Dilimler video dakikasıdır; devre arası ve uzatma ayrılmaz.
  - Pres yalnız top görünürken ve rakip topa sahipken sayılır; top izi zayıfsa boş kalır.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict
from typing import Any

from app.domain import TrackingFrame
from app.engine.tracking.compute import compute_pressure, compute_team_shape
from app.engine.tracking_signals.compute import (
    COMPACTNESS_DELTA_M,
    MIN_PLAYERS,
    PRESS_DELTA,
    WIDTH_DELTA_M,
)

MIN_SLICE_FRAMES = 30
MIN_PRESS_FRAMES = 20
MIN_FORMATION_SUPPORT = 0.5  # karelerin yarısından azında görülen yerleşim yazılmaz
DEPTH_DELTA_M = WIDTH_DELTA_M

LIMITS = (
    "Saha yönü bilinmediği için savunma hattı ve blok yüksekliği verilmez.",
    "Takım ayrımı forma rengine dayanır; yanlış takıma düşen oyuncu genişlik ve derinliği büyütür.",
    "Dilimler video dakikasıdır; devre arası ve uzatma ayrılmaz.",
    "Pres yalnız top görünürken ve rakip topa sahipken sayılır.",
    f"Yerleşim yalnız karelerin en az %{MIN_FORMATION_SUPPORT * 100:.0f}'sinde aynı çıkarsa yazılır; gerçek maçta çoğu dilimde boş kalır.",
    f"Güvenilir dilim: en az {MIN_SLICE_FRAMES} kare ve ortalama {MIN_PLAYERS:g} görünür oyuncu.",
)

_SHAPE_KEYS = ("width_m", "depth_m", "compactness_m", "centroid_x", "centroid_y")
_FINDINGS = (
    ("compactness_m", COMPACTNESS_DELTA_M, "blok açıldı", "blok sıkıştı"),
    ("width_m", WIDTH_DELTA_M, "genişledi", "daraldı"),
    ("depth_m", DEPTH_DELTA_M, "boyu uzadı", "boyu kısaldı"),
)

Slice = tuple[float, float, Sequence[TrackingFrame]]


def _team_slice(team_id: int, frames: Sequence[TrackingFrame]) -> dict[str, Any]:
    shape = asdict(compute_team_shape(team_id, frames).value)
    press = asdict(compute_pressure(team_id, frames).value)
    reliable = shape["frames_used"] >= MIN_SLICE_FRAMES and shape["players_mean"] >= MIN_PLAYERS
    return {
        "reliable": reliable,
        "frames_used": shape["frames_used"],
        "players_mean": shape["players_mean"],
        **{k: shape[k] for k in _SHAPE_KEYS},
        "formation": shape["formation"] if shape["formation_support"] >= MIN_FORMATION_SUPPORT else None,
        "formation_support": shape["formation_support"],
        "press_index": press["press_index"] if press["frames_used"] >= MIN_PRESS_FRAMES else None,
        "press_frames": press["frames_used"],
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Güvenilir dilimlerin kare ağırlıklı ortalaması; hiç yoksa None."""
    good = [r for r in rows if r["reliable"]]
    total = sum(r["frames_used"] for r in good)
    if not total:
        return None
    out: dict[str, Any] = {
        k: round(sum(r[k] * r["frames_used"] for r in good) / total, 1) for k in _SHAPE_KEYS
    }
    press = [r for r in good if r["press_index"] is not None]
    press_total = sum(r["press_frames"] for r in press)
    out["press_index"] = (
        round(sum(r["press_index"] * r["press_frames"] for r in press) / press_total, 2) if press_total else None
    )
    out["reliable_slices"] = len(good)
    return out


def _findings(side: str, rows: list[dict[str, Any]], mean: dict[str, Any], bounds: list[tuple[float, float]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row, (start, end) in zip(rows, bounds, strict=True):
        if not row["reliable"]:
            continue
        for key, threshold, grew, shrank in _FINDINGS:
            delta = round(row[key] - mean[key], 1)
            if abs(delta) >= threshold:
                out.append({"side": side, "from_minute": start, "to_minute": end, "metric": key,
                            "delta": delta, "text": grew if delta > 0 else shrank})
        if row["press_index"] is not None and mean["press_index"] is not None:
            delta = round(row["press_index"] - mean["press_index"], 2)
            if abs(delta) >= PRESS_DELTA:
                out.append({"side": side, "from_minute": start, "to_minute": end, "metric": "press_index",
                            "delta": delta, "text": "pres arttı" if delta > 0 else "pres düştü"})
    return out


def build_match_report(home_team_id: int, away_team_id: int, slices: Sequence[Slice]) -> dict[str, Any]:
    """Dilimler: (başlangıç dk, bitiş dk, kareler). Çıktı JSON'a hazır sözlüktür."""
    bounds = [(start, end) for start, end, _frames in slices]
    teams = {"home": home_team_id, "away": away_team_id}
    per_side = {side: [_team_slice(tid, frames) for _s, _e, frames in slices] for side, tid in teams.items()}
    summary = {side: _summary(rows) for side, rows in per_side.items()}
    findings: list[dict[str, Any]] = []
    for side, rows in per_side.items():
        mean = summary[side]
        if mean is not None:
            findings += _findings(side, rows, mean, bounds)
    return {
        "teams": {side: {"team_external_id": tid, "summary": summary[side]} for side, tid in teams.items()},
        "slices": [
            {"from_minute": start, "to_minute": end, "frames": len(frames),
             "home": per_side["home"][i], "away": per_side["away"][i]}
            for i, (start, end, frames) in enumerate(slices)
        ],
        "findings": sorted(findings, key=lambda f: (f["from_minute"], f["side"], f["metric"])),
        "thresholds": {"compactness_m": COMPACTNESS_DELTA_M, "width_m": WIDTH_DELTA_M,
                       "depth_m": DEPTH_DELTA_M, "press_index": PRESS_DELTA},
        "limits": list(LIMITS),
    }
