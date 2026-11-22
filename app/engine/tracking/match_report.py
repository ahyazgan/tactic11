"""Maç raporu — takip karelerinden dilim dilim takım şekli ve pres, tek yanıtta.

`compute_team_shape` ve `compute_pressure` her dilime ayrı uygulanır; maç özeti
güvenilir dilimlerin kare ağırlıklı ortalamasıdır. Bir dilim, ortalamadan
`tracking_signals` eşikleri kadar saparsa "bulgu" olarak işaretlenir.

Saha yönü: operatör ev sahibinin videonun ilk yarısındaki hücum yönünü (`home_attack`, ±1) ve
tam maç tek videoysa devre arasının video dakikasını (`halftime_minute`) verir; verilmezse yön
kaleci/en derin oyuncudan çıkarılır (space_map kuralı). Yön bilinen dilimlerde **savunma hattı**
yazılır: kaleci düşülmüş en geri hattın kendi kalesine uzaklığı (m, `shape_watch.sample_frame`),
dilimdeki karelerin medyanı; blok etiketi telestrasyonla aynı eşiklerdendir.

Sınırlar (yanıtta `limits` olarak da döner):
  - `centroid_x` ham saha yüzdesidir, "blok yüksekliği" değildir.
  - Savunma hattı tüm karelerden alınır (topa sahipken de); sahiplik ayrımı yoktur.
  - Takım ayrımı renge dayanır; yanlış takıma düşen oyuncu genişlik ve derinliği büyütür.
  - Dilimler video dakikasıdır; devre arası ve uzatma ayrılmaz.
  - Pres yalnız top görünürken ve rakip topa sahipken sayılır; top izi zayıfsa boş kalır.
  - Derinlik bulgu üretmez: gerçek konuma karşı iki gündüz sahasında derinlik bulgularının
    22'sinden 6'sı doğru çıktı (docs/measurements/match-report-vs-gt.json). Sayı tabloda kalır.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import asdict
from statistics import median
from typing import Any

from app.domain import TrackingFrame
from app.engine.shape_watch.compute import block_label, sample_frame
from app.engine.space_map.compute import infer_attack_direction
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
MIN_LINE_SAMPLES = 20        # savunma hattı için dilimde hat bulunan kare

NO_DIRECTION_LIMIT = "Saha yönü bilinmediği için savunma hattı ve blok yüksekliği verilmez."
LINE_LIMITS = (
    "Savunma hattı: kaleci düşülmüş en geri hattın kendi kalesine uzaklığı, dilimdeki karelerin "
    "medyanı; topa sahip olunan kareler de sayılır. Blok: < 30 m alçak, 30–45 m orta, üstü yüksek.",
    "Saha yönü operatör girdisinden gelmediyse kaleci/en derin oyuncudan çıkarılır; gerçek görüntüde "
    "kaleciler çoğu zaman görünmediği için çıkarım çoğunlukla başarısız olur.",
    "Tam maç tek videoysa devre arası dakikası verilmeden ikinci yarının yönü ters kabul edilmez.",
    "Gerçek konuma karşı (2 gündüz maçı, 10'ar dk, yön verilmiş): 5 dk dilimde savunma hattı medyan "
    "0,5–0,7 m sapar, blok etiketi dilimlerin %75–100'ünde aynı; tek dakikalık dilimde hat seyrek de "
    "olsa 25 m'ye varan hatayla yanlış oyuncu kümesine oturabilir (docs/measurements/match-report-def-line-vs-gt.json).",
)
LIMITS = (
    "Takım ayrımı forma rengine dayanır; yanlış takıma düşen oyuncu genişlik ve derinliği büyütür.",
    "Dilimler video dakikasıdır; devre arası ve uzatma ayrılmaz.",
    "Pres yalnız top görünürken ve rakip topa sahipken sayılır; karedeki sahiplik bilgisi gerçek "
    "dokunuşlara karşı bir gündüz maçında sahiplik anlarının %58'inde dolu, dolu olduğunda %85 doğru.",
    f"Yerleşim yalnız karelerin en az %{MIN_FORMATION_SUPPORT * 100:.0f}'sinde aynı çıkarsa yazılır; gerçek maçta çoğu dilimde boş kalır.",
    f"Güvenilir dilim: en az {MIN_SLICE_FRAMES} kare ve ortalama {MIN_PLAYERS:g} görünür oyuncu.",
    "Derinlik (takım boyu) bulgu üretmez: gerçek konuma karşı ölçümde bu bulguların çoğu yanlış çıktı; "
    "tablodaki derinlik değeri 10 m'yi aşan hata taşıyabilir.",
    "Gerçek konuma karşı (2 gündüz maçı, 10'ar dk, dakikalık dilim): pres ve genişlik bulgularının "
    "yaklaşık 3'te 2'si doğru; genişliğin mutlak değeri 3–5 m sapar, dilimler arası değişimi daha güvenilirdir.",
)

_SHAPE_KEYS = ("width_m", "depth_m", "compactness_m", "centroid_x", "centroid_y")
_FINDINGS = (
    ("compactness_m", COMPACTNESS_DELTA_M, "blok açıldı", "blok sıkıştı"),
    ("width_m", WIDTH_DELTA_M, "genişledi", "daraldı"),
)

Slice = tuple[float, float, Sequence[TrackingFrame]]
PartKey = tuple[int, bool]  # (devre, devre arası dakikasından sonra mı)
Direction = Callable[[TrackingFrame, int], int]


def attack_directions(frames: Sequence[TrackingFrame], home: int, away: int, home_attack: int = 0,
                      halftime_minute: float | None = None) -> tuple[Direction, dict[str, Any]]:
    """Kare ve takım → hücum yönü (+1 x artan, -1 azalan, 0 bilinmiyor) ve rapor için özet.

    Bölüm = (devre, devre arası dakikasından sonra mı). Çift devre ya da devre arası sonrası
    ev sahibinin ilk yönünün tersidir; operatör yönü yoksa her bölümde ayrı çıkarılır."""
    if home_attack not in (-1, 0, 1):
        raise ValueError("home_attack -1, 0 veya 1 olmalı")

    def part(f: TrackingFrame) -> PartKey:
        return f.period, halftime_minute is not None and f.minute >= halftime_minute

    groups: dict[PartKey, list[TrackingFrame]] = defaultdict(list)
    for f in frames:
        groups[part(f)].append(f)
    home_dir: dict[PartKey, int] = {}
    methods: dict[PartKey, str] = {}
    for key, members in groups.items():
        if home_attack:
            flipped = (key[0] % 2 == 0) != key[1]
            home_dir[key], methods[key] = (-home_attack if flipped else home_attack), "operator"
        else:
            home_dir[key], methods[key] = infer_attack_direction(members, home, away)

    def direction(f: TrackingFrame, team: int) -> int:
        d = home_dir.get(part(f), 0)
        return d if team == home else -d

    parts = [{"period": k[0], "after_halftime": k[1], "home_attack": home_dir[k], "method": methods[k]}
             for k in sorted(groups)]
    return direction, {"home_attack": home_attack, "halftime_minute": halftime_minute, "parts": parts,
                       "known": any(p["home_attack"] for p in parts)}


def _def_line(team_id: int, frames: Sequence[TrackingFrame], direction: Direction) -> tuple[float | None, int]:
    depths = [s.block_depth for f in frames
              if (s := sample_frame(f, team_id, direction(f, team_id))) is not None]
    return (round(median(depths), 1) if len(depths) >= MIN_LINE_SAMPLES else None), len(depths)


def _team_slice(team_id: int, frames: Sequence[TrackingFrame], direction: Direction) -> dict[str, Any]:
    shape = asdict(compute_team_shape(team_id, frames).value)
    press = asdict(compute_pressure(team_id, frames).value)
    reliable = shape["frames_used"] >= MIN_SLICE_FRAMES and shape["players_mean"] >= MIN_PLAYERS
    def_line, line_frames = _def_line(team_id, frames, direction)
    return {
        "reliable": reliable,
        "frames_used": shape["frames_used"],
        "players_mean": shape["players_mean"],
        **{k: shape[k] for k in _SHAPE_KEYS},
        "formation": shape["formation"] if shape["formation_support"] >= MIN_FORMATION_SUPPORT else None,
        "formation_support": shape["formation_support"],
        "press_index": press["press_index"] if press["frames_used"] >= MIN_PRESS_FRAMES else None,
        "press_frames": press["frames_used"],
        "def_line_m": def_line,
        "line_frames": line_frames,
        "block": block_label(def_line) if def_line is not None else None,
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
    lines = [r for r in good if r["def_line_m"] is not None]
    line_total = sum(r["line_frames"] for r in lines)
    out["def_line_m"] = (
        round(sum(r["def_line_m"] * r["line_frames"] for r in lines) / line_total, 1) if line_total else None
    )
    out["block"] = block_label(out["def_line_m"]) if out["def_line_m"] is not None else None
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


def build_match_report(home_team_id: int, away_team_id: int, slices: Sequence[Slice], *,
                       home_attack: int = 0, halftime_minute: float | None = None) -> dict[str, Any]:
    """Dilimler: (başlangıç dk, bitiş dk, kareler). Çıktı JSON'a hazır sözlüktür."""
    bounds = [(start, end) for start, end, _frames in slices]
    teams = {"home": home_team_id, "away": away_team_id}
    direction, direction_info = attack_directions(
        [f for _s, _e, frames in slices for f in frames], home_team_id, away_team_id, home_attack, halftime_minute)
    per_side = {side: [_team_slice(tid, frames, direction) for _s, _e, frames in slices]
                for side, tid in teams.items()}
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
                       "press_index": PRESS_DELTA},
        "direction": direction_info,
        "limits": [*(LINE_LIMITS if direction_info["known"] else (NO_DIRECTION_LIMIT,)), *LIMITS],
    }
