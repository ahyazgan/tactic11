"""Fiziksel yük — takip izlerinden takım düzeyinde koşu temposu ve hız bölgeleri.

Ham kare-kare hız konum titremesiyle şişer (yükleme yolunda oyuncu-zamanın %8,5'i
"sprint" görünür). Burada her izin konumu `SMOOTH_SECONDS` genişliğinde ortalanmış
kayan ortalamayla düzeltilir, hız düzeltilmiş konumların farkından alınır.

Çıktı oyuncu bazında DEĞİLDİR: iz kimlikleri oyuncular arasında kayar. Verilen
değerler takımın izlenen oyuncu-dakikası başına ortalamadır.

Sınırlar (yanıtta `limits` olarak da döner):
  - Yalnız izlenen oyuncu-zaman sayılır; izlenmeyen oyuncunun koşusu yoktur.
  - Takım ayrımı forma rengine dayanır; hakem ya da rakip takıma karışabilir.
  - `MAX_SPEED_MPS` üstü adımlar (kimlik sıçraması) atılır.
  - Yükleme yolunda gerçek konuma karşı doğrulanmadı.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

SMOOTH_SECONDS = 1.0
MAX_GAP_SECONDS = 1.0
MAX_SPEED_MPS = 12.0
HSR_MPS = 5.5       # match_squad fiziksel örnek sözleşmesiyle aynı eşikler
SPRINT_MPS = 7.0
SQUAD_SIZE = 11
MIN_COVERAGE = 0.5  # dilimde takımın oyuncu-zamanının en az yarısı izlenmiş olmalı

LIMITS = (
    "Oyuncu bazında değildir: değerler takımın izlenen oyuncu-dakikası başına ortalamadır.",
    "Yalnız izlenen oyuncu-zaman sayılır; kapsama düşükse dilim güvenilmez işaretlenir.",
    f"Hız, konumun {SMOOTH_SECONDS:g} sn'lik kayan ortalamasından alınır; {MAX_SPEED_MPS:g} m/sn üstü adımlar atılır.",
    f"Yüksek hız > {HSR_MPS:g} m/sn, sprint > {SPRINT_MPS:g} m/sn; paylar izlenen oyuncu-zamana göredir.",
    "Yükleme yolunda gerçek konuma karşı henüz doğrulanmadı.",
)

# İz örneği: (saniye, x metre, y metre, takım kimliği ya da None)
Sample = tuple[float, float, float, int | None]
_KEYS = ("seconds", "distance_m", "hsr_seconds", "sprint_seconds")


def track_steps(samples: Sequence[Sample]) -> list[tuple[float, float, float, int | None]]:
    """Bir izin geçerli adımları: (adım ortası sn, süre sn, mesafe m, takım)."""
    ordered = sorted(samples, key=lambda s: s[0])
    if len(ordered) < 3:
        return []
    t = np.array([s[0] for s in ordered], dtype=float)
    xy = np.array([s[1:3] for s in ordered], dtype=float)
    out: list[tuple[float, float, float, int | None]] = []
    for seg in np.split(np.arange(len(t)), np.where(np.diff(t) > MAX_GAP_SECONDS)[0] + 1):
        if len(seg) < 3:
            continue
        ts, ps = t[seg], xy[seg]
        lo = np.searchsorted(ts, ts - SMOOTH_SECONDS / 2, "left")
        hi = np.searchsorted(ts, ts + SMOOTH_SECONDS / 2, "right")
        sums = np.vstack([np.zeros(2), np.cumsum(ps, axis=0)])
        smooth = (sums[hi] - sums[lo]) / (hi - lo)[:, None]
        dt = np.diff(ts)
        dist = np.hypot(*np.diff(smooth, axis=0).T)
        for k in np.where((dt > 0) & (dist <= MAX_SPEED_MPS * dt))[0]:
            out.append((float(ts[k] + dt[k] / 2), float(dt[k]), float(dist[k]), ordered[int(seg[k])][3]))
    return out


def _empty() -> dict[str, float]:
    return dict.fromkeys(_KEYS, 0.0)


def _add(total: dict[str, float], dt: float, dist: float) -> None:
    speed = dist / dt
    total["seconds"] += dt
    total["distance_m"] += dist
    total["hsr_seconds"] += dt if speed > HSR_MPS else 0.0
    total["sprint_seconds"] += dt if speed > SPRINT_MPS else 0.0


def rates(total: Mapping[str, float]) -> dict[str, Any]:
    """Toplamlardan oranlar; hiç oyuncu-zaman yoksa değerler None."""
    seconds = total["seconds"]
    if seconds <= 0:
        return {"player_minutes": 0.0, "m_per_player_min": None, "hsr_share": None, "sprint_share": None}
    return {
        "player_minutes": round(seconds / 60, 1),
        "m_per_player_min": round(total["distance_m"] / seconds * 60, 1),
        "hsr_share": round(total["hsr_seconds"] / seconds, 4),
        "sprint_share": round(total["sprint_seconds"] / seconds, 4),
    }


def total_load(tracks: Mapping[int, Sequence[Sample]]) -> dict[str, float]:
    """Takım ayırmadan tüm izlerin toplamı (doğrulama araçları için)."""
    total = _empty()
    for samples in tracks.values():
        for _mid, dt, dist, _team in track_steps(samples):
            _add(total, dt, dist)
    return total


def compute_physical_load(
    tracks: Mapping[int, Sequence[Sample]], home_team_id: int, away_team_id: int,
    bounds: Sequence[tuple[float, float]],
) -> dict[str, Any]:
    """Dilim sınırları dakika cinsinden (başlangıç, bitiş); çıktı JSON'a hazır."""
    sides = {home_team_id: "home", away_team_id: "away"}
    totals = [{"home": _empty(), "away": _empty()} for _ in bounds]
    for samples in tracks.values():
        for mid, dt, dist, team in track_steps(samples):
            side = sides.get(team) if team is not None else None
            if side is None:
                continue
            minute = mid / 60
            for i, (start, end) in enumerate(bounds):
                if start <= minute < end:
                    _add(totals[i][side], dt, dist)
                    break
    slices: list[dict[str, Any]] = []
    summary = {"home": _empty(), "away": _empty()}
    for (start, end), per_side in zip(bounds, totals, strict=True):
        row: dict[str, Any] = {"from_minute": start, "to_minute": end}
        for side, total in per_side.items():
            coverage = total["seconds"] / 60 / ((end - start) * SQUAD_SIZE)
            reliable = coverage >= MIN_COVERAGE
            row[side] = {"reliable": reliable, "coverage": round(coverage, 2), **rates(total)}
            if reliable:
                for key in _KEYS:
                    summary[side][key] += total[key]
        slices.append(row)
    return {
        "teams": {side: (rates(total) if total["seconds"] > 0 else None) for side, total in summary.items()},
        "slices": slices,
        "limits": list(LIMITS),
    }
