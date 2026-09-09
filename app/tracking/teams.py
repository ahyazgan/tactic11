"""Takım ataması — forma rengi kümeleme (saf numpy).

Her takip (track) için gövde bölgesinin ortalama rengi biriktirilir; klip
sonunda k=3 k-means (çoklu başlangıç, en düşük atalet) çalışır: en kalabalık
iki küme takım 0/1, üçüncü küme (hakem, kaleci, seyirci) None. Merkezine
uzak kalan takipler de None alır.

Kimlik yine "tahmini": takım bilinir, oyuncu bilinmez.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import numpy as np


def torso_color(frame_rgb: np.ndarray, xyxy: tuple[float, float, float, float]) -> np.ndarray | None:
    """bbox'ın gövde bölgesinin (forma) ortalama RGB'si; çim pikselleri hariç.

    Tepeden bakışta kutu küçüktür (30×40 px); bölge geniş tutulur (yükseklik
    %10–70, genişlik %15–85) ki yeterli forma pikseli kalsın.
    """
    x1, y1, x2, y2 = (round(v) for v in xyxy)
    h, w = frame_rgb.shape[:2]
    x1, x2 = max(0, x1), min(w, x2)
    y1, y2 = max(0, y1), min(h, y2)
    if x2 - x1 < 2 or y2 - y1 < 4:
        return None
    bw, bh = x2 - x1, y2 - y1
    cx1, cx2 = x1 + int(bw * 0.15), x1 + int(bw * 0.85)
    cy1, cy2 = y1 + int(bh * 0.10), y1 + int(bh * 0.70)
    crop = frame_rgb[cy1:cy2, cx1:cx2].reshape(-1, 3).astype(float)
    if crop.size == 0:
        return None
    r, g, b = crop[:, 0], crop[:, 1], crop[:, 2]
    not_grass = ~((g > r * 1.12) & (g > b * 1.12))
    kept = crop[not_grass]
    if len(kept) < max(4, len(crop) * 0.12):
        kept = crop
    return kept.mean(axis=0)


def kmeans(features: np.ndarray, k: int, *, iters: int = 30, n_init: int = 8, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """k-means (k-means++ başlangıç, n_init deneme, en düşük atalet). Dönen: labels, centers."""
    X = np.asarray(features, dtype=float)
    n = len(X)
    if n == 0:
        return np.zeros(0, dtype=int), np.zeros((k, 3))
    if n <= k:
        centers = np.vstack([X, np.repeat(X[-1:], k - n, axis=0)]) if n < k else X.copy()
        return np.arange(n), centers
    rng = np.random.default_rng(seed)
    best_labels, best_centers, best_inertia = None, None, np.inf
    for _ in range(n_init):
        # k-means++
        picked = [X[rng.integers(n)]]
        for _k in range(1, k):
            d2 = np.min([np.sum((X - c) ** 2, axis=1) for c in picked], axis=0)
            total = float(d2.sum())
            if total <= 0.0:
                # Tüm noktalar seçilmiş merkezlerle ÇAKIŞIYOR (ör. iki forma
                # rengi, k=3 ve renk gürültüsü yok). d2/0 → hepsi sıfır olasılık
                # ve rng.choice "probabilities do not sum to 1" ile ÇÖKER.
                # Böyle bir sahnede k-means++'ın ekleyecek bilgisi yok: rastgele
                # bir nokta al, döngü zaten boş kümeyi eritir.
                picked.append(X[rng.integers(n)])
                continue
            picked.append(X[rng.choice(n, p=d2 / total)])
        centers = np.array(picked)
        labels = np.zeros(n, dtype=int)
        for _ in range(iters):
            dist = np.stack([np.linalg.norm(X - c, axis=1) for c in centers], axis=1)
            new_labels = dist.argmin(axis=1)
            if np.array_equal(new_labels, labels) and _ > 0:
                break
            labels = new_labels
            for j in range(k):
                if np.any(labels == j):
                    centers[j] = X[labels == j].mean(axis=0)
        inertia = float(sum(np.sum((X[labels == j] - centers[j]) ** 2) for j in range(k)))
        if inertia < best_inertia:
            best_inertia, best_labels, best_centers = inertia, labels.copy(), centers.copy()
    assert best_labels is not None and best_centers is not None
    return best_labels, best_centers


def kmeans2(features: np.ndarray, *, iters: int = 25, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """İki merkezli k-means (geri uyum)."""
    return kmeans(features, 2, iters=iters, seed=seed)


@dataclass
class TeamAssignment:
    team_by_track: dict[int, int | None]
    centers: np.ndarray
    outlier_tracks: frozenset[int]


def _order_by_anchor(
    centers: np.ndarray, team_clusters: list[int], anchor: np.ndarray,
) -> list[int]:
    """İki takım kümesini çapa renklerine göre sırala → [ev kümesi, deplasman kümesi].

    İki olası eşleşmeden (düz / çapraz) toplam renk mesafesi küçük olan seçilir;
    böylece bir segmentte "kırmızı = ev" ise sonraki segmentlerde de öyle kalır.
    """
    a, b = team_clusters[0], team_clusters[1]
    straight = (float(np.linalg.norm(centers[a] - anchor[0]))
                + float(np.linalg.norm(centers[b] - anchor[1])))
    crossed = (float(np.linalg.norm(centers[b] - anchor[0]))
               + float(np.linalg.norm(centers[a] - anchor[1])))
    return [b, a] if crossed < straight else [a, b]


class TeamAssigner:
    """Takip başına renk gözlemi biriktirir; `fit()` ile 0/1/None atar."""

    def __init__(self, *, outlier_factor: float = 2.5, min_observations: int = 2) -> None:
        self._obs: dict[int, list[np.ndarray]] = defaultdict(list)
        self._outlier_factor = outlier_factor
        self._min_obs = min_observations

    def observe(self, track_id: int, color: np.ndarray | None) -> None:
        if color is not None:
            self._obs[track_id].append(np.asarray(color, dtype=float))

    def fit(self, anchor_colors: np.ndarray | None = None) -> TeamAssignment:
        """Renk kümelerini 0 (ev) / 1 (deplasman) takımına ata.

        `anchor_colors` (2×3) verilirse takım kimliği küme BÜYÜKLÜĞÜNE değil bu
        renklere göre belirlenir. Canlı akışta zorunlu: her segment ayrı fit
        edildiği için, en kalabalık kümeyi ev sahibi saymak segmentler arasında
        takımların yer değiştirmesine yol açar (kadraja giren oyuncu sayısı
        değişir) — o zaman "rakip daraldı" sinyali yanlış takımı gösterir.
        """
        tracks = [t for t, obs in self._obs.items() if len(obs) >= self._min_obs]
        if len(tracks) < 2:
            return TeamAssignment({t: None for t in self._obs}, np.zeros((2, 3)), frozenset(self._obs))
        feats = np.array([np.median(np.vstack(self._obs[t]), axis=0) for t in tracks])
        k = 3 if len(tracks) >= 6 else 2
        labels, centers = kmeans(feats, k)
        sizes = [(int(np.sum(labels == j)), j) for j in range(k)]
        sizes.sort(reverse=True)
        team_clusters = [j for _, j in sizes[:2]]
        if anchor_colors is not None and len(anchor_colors) == 2:
            team_clusters = _order_by_anchor(centers, team_clusters, np.asarray(anchor_colors, dtype=float))
        cluster_to_team = {team_clusters[0]: 0, team_clusters[1]: 1}

        dist_own = np.array([np.linalg.norm(feats[i] - centers[labels[i]]) for i in range(len(tracks))])
        spread = float(np.median(dist_own)) if len(dist_own) else 0.0
        threshold = max(spread * self._outlier_factor, 30.0)

        team_by_track: dict[int, int | None] = {}
        outliers: set[int] = set()
        for i, t in enumerate(tracks):
            team = cluster_to_team.get(int(labels[i]))
            if team is None or dist_own[i] > threshold:
                team_by_track[t] = None
                outliers.add(t)
            else:
                team_by_track[t] = team
        for t in self._obs:
            if t not in team_by_track:
                team_by_track[t] = None
                outliers.add(t)
        return TeamAssignment(team_by_track, centers[team_clusters], frozenset(outliers))
