"""Takım ataması — forma rengi kümeleme (saf numpy).

Her takip (track) için gövde bölgesinin FORMA rengi biriktirilir; klip sonunda
k=2 k-means (çoklu başlangıç, en düşük atalet) çalışır: iki küme takım 0/1,
merkezine uzak kalan takipler (hakem, kaleci, seyirci) None alır.

## Ölçüm (SoccerTrack v2 117092, gece panoraması, 540 GT-etiketli tespit, 43 kare)

Kare başına kümeleme doğruluğu (iki büyük küme ↔ iki takım, en iyi eşleme):

    gövde ortalama RGB, k=3 (eski)   %55
    gövde ortalama RGB, k=2          %69
    parlak %40 piksel RGB, k=3       %62
    parlak %40 piksel RGB, k=2       %80  ← şimdiki

k=2 sonrası medyan yeniden-merkezleme (`median_recenter`, hakem koruması) aynı
verinin 8 karelik alt kümesinde doğruluğu değiştirmedi (k=2 %87 = %87; k=3 %65).

Neden: gece/küçük kutuda (30×50 px) gövde bölgesinin ortalaması karanlık arka
planla doluyor, iki takım da "koyu gri" çıkıyordu (küme merkezleri 82/59).
Forma, bölgedeki EN PARLAK piksellerdir; onların ortalaması beyaz–mavi ayrımını
korur. k=3'te beyaz formalar gölge/ışık diye ikiye bölünüp maviyle karışıyordu;
üçüncü grup (hakem/kaleci) zaten uzaklık eşiğiyle None'a düşer.

2026-09-14: yalnız RGB uzaklığı gece karanlığında farklı renkleri ayıramıyor.
RGB kümeleri korunur; RGB oranı (parlaklıktan bağımsız renk) küme renginden
uzaksa atama da reddedilir. Kısa ömürlü olduğu için takip hattından çıkarılmış
kimlikler merkezlerin öğrenilmesine katılmaz. Ölçüm ve sınırlar:
docs/SABIT-KAMERA-SINYAL-KALITESI.md.

Kimlik yine "tahmini": takım bilinir, oyuncu bilinmez.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import numpy as np

# Forma rengi = gövde bölgesindeki (çim hariç) en parlak piksellerin ortalaması.
BRIGHT_FRACTION = 0.4
# RGB clustering retains brightness to distinguish white/dark kits. A second,
# brightness-independent check rejects differently coloured officials/edge people.
# A 15/255 floor tolerates sensor noise in small night-time shirt crops.
CHROMATICITY_MIN_DISTANCE = 15.0


def chromaticity(colors: np.ndarray) -> np.ndarray:
    """RGB proportions, invariant to a common brightness multiplier."""
    colors = np.asarray(colors, dtype=float)
    return 255.0 * colors / np.maximum(colors.sum(axis=-1, keepdims=True), 1.0)


def torso_color(frame_rgb: np.ndarray, xyxy: tuple[float, float, float, float]) -> np.ndarray | None:
    """bbox'ın gövde bölgesinin FORMA rengi: çim hariç en parlak %40 pikselin ortalama RGB'si.

    Bölge: yükseklik %10–55 (şort hariç), genişlik %20–80. Küçük kutuda (30×50 px)
    düz ortalama arka planla doluyordu; parlak pikseller formayı temsil eder
    (ölçüm modül doküstringinde). Gündüz çim parlak olduğu için çim pikselleri
    önce elenir.
    """
    x1, y1, x2, y2 = (round(v) for v in xyxy)
    h, w = frame_rgb.shape[:2]
    x1, x2 = max(0, x1), min(w, x2)
    y1, y2 = max(0, y1), min(h, y2)
    if x2 - x1 < 2 or y2 - y1 < 4:
        return None
    bw, bh = x2 - x1, y2 - y1
    cx1, cx2 = x1 + int(bw * 0.20), x1 + int(bw * 0.80)
    cy1, cy2 = y1 + int(bh * 0.10), y1 + int(bh * 0.55)
    crop = frame_rgb[cy1:cy2, cx1:cx2].reshape(-1, 3).astype(float)
    if crop.size == 0:
        return None
    r, g, b = crop[:, 0], crop[:, 1], crop[:, 2]
    not_grass = ~((g > r * 1.12) & (g > b * 1.12))
    kept = crop[not_grass]
    if len(kept) < max(4, len(crop) * 0.12):
        kept = crop
    k = max(4, int(len(kept) * BRIGHT_FRACTION))
    brightest = kept[np.argsort(kept.max(axis=1))[-k:]]
    return brightest.mean(axis=0)


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


def median_recenter(features: np.ndarray, labels: np.ndarray, centers: np.ndarray, *, rounds: int = 2) -> tuple[np.ndarray, np.ndarray]:
    """Küme merkezlerini koordinat-medyanına çekip yeniden ata (k=2 için hakem koruması).

    k=2'de üçüncü renk (sarı hakem) en yakın takımın kümesine düşer ve ORTALAMA
    merkezi kendine çeker; takım küçükse (4 oyuncu + 2 hakem) oyuncular kendi
    merkezlerinden uzaklaşıp aykırı sayılır. Medyan merkez çoğunluğun (forma)
    rengini korur; hakem sonra uzaklık eşiğiyle None'a düşer.
    """
    X = np.asarray(features, dtype=float)
    labels = labels.copy()
    centers = centers.copy()
    for _ in range(rounds):
        for j in range(len(centers)):
            if np.any(labels == j):
                centers[j] = np.median(X[labels == j], axis=0)
        dist = np.stack([np.linalg.norm(X - c, axis=1) for c in centers], axis=1)
        new_labels = dist.argmin(axis=1)
        if np.array_equal(new_labels, labels):
            break
        labels = new_labels
    return labels, centers


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

    def __init__(self, *, outlier_factor: float = 2.5, min_observations: int = 2,
                 reject_color_outliers: bool = True) -> None:
        self._obs: dict[int, list[np.ndarray]] = defaultdict(list)
        self._outlier_factor = outlier_factor
        self._min_obs = min_observations
        self._reject_color_outliers = reject_color_outliers

    def observe(self, track_id: int, color: np.ndarray | None) -> None:
        if color is not None:
            self._obs[track_id].append(np.asarray(color, dtype=float))

    def fit(
        self, anchor_colors: np.ndarray | None = None, *,
        eligible_tracks: set[int] | None = None,
    ) -> TeamAssignment:
        """Renk kümelerini 0 (ev) / 1 (deplasman) takımına ata.

        `anchor_colors` (2×3) verilirse takım kimliği küme BÜYÜKLÜĞÜNE değil bu
        renklere göre belirlenir. Canlı akışta zorunlu: her segment ayrı fit
        edildiği için, en kalabalık kümeyi ev sahibi saymak segmentler arasında
        takımların yer değiştirmesine yol açar (kadraja giren oyuncu sayısı
        değişir) — o zaman "rakip daraldı" sinyali yanlış takımı gösterir.
        """
        # Takip hattının kısa ömürlü/gürültü sayıp attığı kimlikler renk
        # merkezlerini de etkilememeli. Aksi halde görüntüden silinen sahte
        # takipler iki forma renginden birini hâlâ ele geçirebilir.
        tracks = [t for t, obs in self._obs.items() if len(obs) >= self._min_obs
                  and (eligible_tracks is None or t in eligible_tracks)]
        if len(tracks) < 2:
            return TeamAssignment({t: None for t in self._obs}, np.zeros((2, 3)), frozenset(self._obs))
        feats = np.array([np.median(np.vstack(self._obs[t]), axis=0) for t in tracks])
        # k=2: iki takım; hakem/kaleci uzaklık eşiğiyle None'a düşer. k=3 beyaz
        # formayı gölge/ışık diye bölüp maviyle karıştırıyordu (ölçüm: modül doküstringi).
        k = 2
        labels, centers = kmeans(feats, k)
        labels, centers = median_recenter(feats, labels, centers)
        sizes = [(int(np.sum(labels == j)), j) for j in range(k)]
        sizes.sort(reverse=True)
        team_clusters = [j for _, j in sizes[:2]]
        if anchor_colors is not None and len(anchor_colors) == 2:
            team_clusters = _order_by_anchor(centers, team_clusters, np.asarray(anchor_colors, dtype=float))
        cluster_to_team = {team_clusters[0]: 0, team_clusters[1]: 1}

        dist_own = np.array([np.linalg.norm(feats[i] - centers[labels[i]]) for i in range(len(tracks))])
        spread = float(np.median(dist_own)) if len(dist_own) else 0.0
        threshold = max(spread * self._outlier_factor, 30.0)
        tint_dist = np.linalg.norm(chromaticity(feats) - chromaticity(centers)[labels], axis=1)
        tint_thresholds = {
            j: max(float(np.median(tint_dist[labels == j])) * self._outlier_factor,
                   CHROMATICITY_MIN_DISTANCE)
            for j in range(k) if np.any(labels == j)
        }

        team_by_track: dict[int, int | None] = {}
        outliers: set[int] = set()
        for i, t in enumerate(tracks):
            team = cluster_to_team.get(int(labels[i]))
            wrong_color = (self._reject_color_outliers
                           and tint_dist[i] > tint_thresholds[int(labels[i])])
            if team is None or dist_own[i] > threshold or wrong_color:
                team_by_track[t] = None
                outliers.add(t)
            else:
                team_by_track[t] = team
        for t in self._obs:
            if t not in team_by_track:
                team_by_track[t] = None
                outliers.add(t)
        return TeamAssignment(team_by_track, centers[team_clusters], frozenset(outliers))
