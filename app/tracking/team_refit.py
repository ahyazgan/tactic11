"""Takım atamasını forma renk ORANIYLA yeniden kur (frames JSON + kit_colors üzerinde).

Dondurulmuş `teams.py` takipleri parlaklık taşıyan RGB'de kümeler. Güneşli sahada
uzak/küçük oyuncular (iki takımdan da) beyaza yakın çıkıp aynı kümeye düşer;
132831'de göz etiketli kutularda "soluk" 16 oyuncunun hepsi ev sahibi sayıldı
(docs/TAKIM-AYRIMI-GUNES.md). Burada özellik, gövde ortanca renginin oranıdır
(255·RGB/ΣRGB): ortak parlaklık çarpanından bağımsızdır, mavi/sarı/beyaz ayrımını
korur.

Akış (segment başına, `scripts.track_live_candidates` çıktısı):
1. `kit_colors/<seg>.json` → takip başına ortanca gövde rengi → renk oranı.
2. Renk oranlarının birinci ana bileşeni (iki forma arasındaki baskın renk
   ekseni) üzerine izdüşüm; karar eşiği eksen üzerindeki NÖTR GRİ noktasıdır
   (beyaza dönen forma hangi tona yakınsa o takım), iki 1-B küme merkezinin
   arasında `NEUTRAL_BAND` payıyla sınırlanır (bir takım beyaz giyiyorsa gri
   noktası o kümenin üstüne düşer; o zaman eşik ortaya çekilir). 3 boyutlu
   kümeleme ve 1-B küme ortası, soluk mavi oyuncuyu beyaz kümeye atıyordu
   (dev ölçümü, docs/TAKIM-AYRIMI-GUNES.md §2). İki küme merkezi
   `MIN_CHROMA_SEPARATION`'dan yakınsa atama değiştirilmez (tek renk / belirsiz).
3. Takım kimliği (hangi küme ev sahibi) ÜRETİM atamasıyla uyuşmaya göre seçilir:
   üretim net renkli oyuncularda doğrudur ve çapası segmentler arası sabittir,
   yeniden atama yalnız soluk/uzak oyuncuları düzeltir. Üretim hiç takım
   atamadıysa (tek renk gördü) küme büyüklüğü ya da verilen çapa kullanılır.
4. İki merkezi birleştiren eksene dik uzaklığı ayrımın `PERP_FACTOR` katından
   büyük takipler None (hakem, farklı renkli kaleci): soluk/beyaza dönmüş oyuncu
   eksenin ÜSTÜNDE kalır ve en yakın takıma gider, başka renk eksenin dışındadır.
5. Karelerdeki `team_external_id` takip kimliğiyle (namespace·stride + 30000 + yerel
   id) yeniden yazılır; üretim ataması `team_external_id_tracking` alanında saklanır.
"""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from app.tracking.frames import VIDEO_PLAYER_BASE_ID
from app.tracking.identity_namespace import LOCAL_ID_STRIDE
from app.tracking.teams import chromaticity, kmeans

MIN_CHROMA_SEPARATION = 8.0    # iki küme merkezi arası (renk oranı birimi, 0–255 ölçeği)
PERP_FACTOR = 0.35             # eksene dik uzaklık / merkezler arası ayrım
NEUTRAL_BAND = 0.25            # gri eşik iki 1-B merkez arasında bu paydan daha kenara gidemez
NEUTRAL_GREY = np.array([85.0, 85.0, 85.0])   # chromaticity([1, 1, 1])
MIN_OBSERVATIONS = 2


@dataclass(frozen=True)
class RefitResult:
    centers: np.ndarray                        # 2×3 renk oranı, [ev, deplasman]
    team_by_track: dict[int, int | None]       # yerel takip kimliği → 0/1/None
    reason: str | None = None                  # None değilse atama yapılmadı


def track_features(kits: dict[str, Any], *, feature: str = "median") -> tuple[list[int], np.ndarray]:
    tids, feats = [], []
    for tid, row in kits["tracks"].items():
        if int(row.get("n", 0)) < MIN_OBSERVATIONS:
            continue
        tids.append(int(tid))
        feats.append(chromaticity(np.asarray(row[feature], dtype=float)))
    return tids, np.asarray(feats, dtype=float).reshape(-1, 3)


def _order_by_anchor(centers: np.ndarray, anchor: np.ndarray) -> list[int]:
    """Küme → takım: merkezlerin çapa renklerine toplam uzaklığını en aza indiren sıra."""
    d = np.linalg.norm(centers[:, None, :] - anchor[None, :, :], axis=-1)
    return [0, 1] if d[0, 0] + d[1, 1] <= d[0, 1] + d[1, 0] else [1, 0]


def refit_teams(kits: dict[str, Any], anchor: np.ndarray | None, *, feature: str = "median",
                production: dict[int, int | None] | None = None) -> RefitResult:
    """`production`: yerel takip kimliği → üretim takımı (0/1/None); küme→takım sırası buna uyar."""
    tids, feats = track_features(kits, feature=feature)
    if len(tids) < 4:
        return RefitResult(np.zeros((2, 3)), {}, "yeterli takip yok")
    mean = feats.mean(axis=0)
    _u, _s, vt = np.linalg.svd(feats - mean, full_matrices=False)
    proj = (feats - mean) @ vt[0]
    labels1, centers1 = kmeans(proj.reshape(-1, 1), 2)
    if len(np.unique(labels1)) < 2:
        return RefitResult(np.zeros((2, 3)), {}, "iki forma renk oranı ayırt edilemiyor")
    lo, hi = sorted(float(c) for c in centers1.ravel())
    grey = float((NEUTRAL_GREY - mean) @ vt[0])
    threshold = min(max(grey, lo + NEUTRAL_BAND * (hi - lo)), hi - NEUTRAL_BAND * (hi - lo))
    labels = (proj > threshold).astype(int)
    if labels.min() == labels.max():
        return RefitResult(np.zeros((2, 3)), {}, "iki forma renk oranı ayırt edilemiyor")
    centers = np.vstack([np.median(feats[labels == j], axis=0) for j in range(2)])
    if float(np.linalg.norm(centers[0] - centers[1])) < MIN_CHROMA_SEPARATION:
        return RefitResult(np.zeros((2, 3)), {}, "iki forma renk oranı ayırt edilemiyor")
    agree: Counter[tuple[int, int]] = Counter()
    for i, t in enumerate(tids):
        prod = (production or {}).get(t)
        if prod in (0, 1):
            agree[(int(labels[i]), prod)] += 1
    if agree:
        order = [0, 1] if agree[(0, 0)] + agree[(1, 1)] >= agree[(0, 1)] + agree[(1, 0)] else [1, 0]
    elif anchor is not None:
        order = _order_by_anchor(centers, anchor)
    else:
        order = sorted(range(2), key=lambda j: -int(np.sum(labels == j)))
    cluster_to_team = {order[0]: 0, order[1]: 1}
    axis = centers[1] - centers[0]
    separation = float(np.linalg.norm(axis))
    rel = feats - centers[0]
    along = rel @ axis / separation
    perp = np.sqrt(np.maximum(np.einsum("ij,ij->i", rel, rel) - along ** 2, 0.0))
    team_by_track = {t: (None if perp[i] > PERP_FACTOR * separation else cluster_to_team[int(labels[i])])
                     for i, t in enumerate(tids)}
    return RefitResult(centers[order], team_by_track)


def apply_refit(frames: list[dict[str, Any]], result: RefitResult, namespace: int,
                home_team_id: int, away_team_id: int) -> dict[str, int]:
    """Karelerdeki takımı yeniden yaz; değişen oyuncu gözlemi sayısını döner."""
    stats = {"changed": 0, "players": 0}
    if result.reason is not None:
        return stats
    team_id = {0: home_team_id, 1: away_team_id, None: None}
    for f in frames:
        for p in f.get("players", []):
            stats["players"] += 1
            local = int(p["player_external_id"]) - namespace * LOCAL_ID_STRIDE - VIDEO_PLAYER_BASE_ID
            if local not in result.team_by_track:
                continue
            new = team_id[result.team_by_track[local]]
            if "team_external_id_tracking" not in p:
                p["team_external_id_tracking"] = p.get("team_external_id")
            if new != p.get("team_external_id"):
                p["team_external_id"] = new
                stats["changed"] += 1
    return stats


def load_anchor(path: Path) -> np.ndarray | None:
    try:
        a = np.asarray(json.loads(path.read_text(encoding="utf-8")), dtype=float)
    except (OSError, ValueError):
        return None
    return a if a.shape == (2, 3) and np.isfinite(a).all() else None


def production_teams(frames: list[dict[str, Any]], namespace: int, home_team_id: int, away_team_id: int,
                     ) -> dict[int, int | None]:
    """Karelerdeki üretim ataması: yerel takip kimliği → 0/1/None (çoğunluk)."""
    votes: dict[int, Counter[int | None]] = {}
    code = {home_team_id: 0, away_team_id: 1}
    for f in frames:
        for p in f.get("players", []):
            local = int(p["player_external_id"]) - namespace * LOCAL_ID_STRIDE - VIDEO_PLAYER_BASE_ID
            team = p.get("team_external_id_tracking", p.get("team_external_id"))
            votes.setdefault(local, Counter())[code.get(team)] += 1
    return {t: c.most_common(1)[0][0] for t, c in votes.items()}


def refit_segment(frames: list[dict[str, Any]], kits: dict[str, Any], anchor_path: Path,
                  home_team_id: int, away_team_id: int, *, feature: str = "median") -> dict[str, Any]:
    """Bir segmentin karelerine yeniden atama uygula; çapa yoksa bu segmentten kur."""
    anchor = load_anchor(anchor_path)
    production = production_teams(frames, int(kits["namespace"]), home_team_id, away_team_id)
    result = refit_teams(kits, anchor, feature=feature, production=production)
    if result.reason is None and anchor is None:
        tmp = anchor_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(result.centers.round(2).tolist()), encoding="utf-8")
        tmp.replace(anchor_path)
    stats = apply_refit(frames, result, int(kits["namespace"]), home_team_id, away_team_id)
    return {**stats, "reason": result.reason, "centers": result.centers.round(1).tolist(),
            "assigned": sum(v is not None for v in result.team_by_track.values()),
            "unassigned": sum(v is None for v in result.team_by_track.values())}
