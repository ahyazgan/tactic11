"""Durum-taban cetveli (karar etkisi v2 ADAYI): "bu durumda olağan olan"a göre ölç.

## Neden bu motor var

Karar etkisi v1 (`decision_impact`) kararı "sonraki 15 dk xG farkı − önceki
15 dk xG farkı" ile puanlar ve mutlak eşiğe (±0.010/dk) vurur. Koç zekâ
karnesinde ölçüldü (100 maç, Barcelona): bu haliyle cetvel ELİT antrenörün
gerçek hamlelerini plasebo dakikalarından ayıramıyor (elit %52, plasebo %54).

Hipotez: sorun kıyastı — 75. dakikada 1-0 önde olan takımın xG akışı düşer,
bu değişikliğin sonucu değil oyun durumunun olağan seyridir. Bu motor kararın
puanını `Δ − olağan(dakika bandı × skor durumu)` yapar; olağan akış tablosu
karar DIŞI anlardan (iki takım perspektifi, kendi değişikliğine ±12 dk uzak,
leave-one-match-out) öğrenilir.

## ÖLÇÜM SONUCU (2026-09-12, `scripts/coach_iq.py`) — kabul ölçütünü GEÇMEDİ

Kabul ölçütü önceden yazıldı: elit − plasebo ≥ 10 puan, hem ham isabette hem
hücre-içi (Mantel-Haenszel) kıyasta. Sonuç, 1594 karar-dışı anlık taban:

    v1 (mutlak):      elit %52 · plasebo %54 · hücre-içi fark +0.054
    v2 (düzeltilmiş): elit %52 · plasebo %58 · hücre-içi fark +0.032

Denenen öteki aday da elendi: beklenen-puan (kazanma olasılığı, Poisson)
cetveli elit %59 / plasebo %60 verdi; pencere 25 ve 45 dk daha kötüydü.

**Ders:** seyrek plasebo (8 sabit dakika, geç bantlarda n≤3) ilk denemede
"+18 puan" göstermişti — küçük hücre gürültüsü. Yoğun ızgarayla (her 5 dk)
fark kayboldu. Küçük-n hücre kıyasına asla tek başına güvenme.

**Sonuç:** 15 dk'lık xG akışı, tek bir değişikliğin etkisini bu n'de (~170-250
elit hamle) görmüyor; cetvel yeniden ağırlıklandırmayla düzelmiyor. Kararın
"sonra ne oldu"su yerine kararın İÇERİĞİ (kim çıktı/girdi, giren oyuncunun
katkısı) ölçülmeli. Bu motor karnede aday olarak kalır: gelecek bir cetvel
aynı üç kümede (elit · motor · plasebo) aynı ölçütü geçmek zorundadır.

Saf fonksiyonlar; DB/IO yok.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

ENGINE_NAME = "engine.decision_baseline"
ENGINE_VERSION = "1"

# Dakika bantları (üst sınır hariç): [0,45) [45,60) [60,70) [70,80) [80,∞)
MINUTE_BANDS: tuple[float, ...] = (45.0, 60.0, 70.0, 80.0)
SCORE_STATES: tuple[str, ...] = ("leading", "drawing", "trailing")
# Hücre bu kadar örnekten azsa genel ortalama kullanılır.
MIN_CELL_N = 8

StateKey = tuple[int, str]


@dataclass(frozen=True)
class BaselineSample:
    minute: float
    score_state: str      # "leading" | "drawing" | "trailing"
    xg_delta: float       # decision_impact.xg_diff_delta (dk başına, sonraki − önceki)


@dataclass(frozen=True)
class CellStat:
    band: int
    score_state: str
    n: int
    mean: float


@dataclass(frozen=True)
class StateBaseline:
    """Hücre → olağan Δxg_diff. `global_mean` görülmemiş/küçük hücre için."""

    cells: dict[StateKey, CellStat]
    global_mean: float
    samples: int

    def expected(self, minute: float, score_state: str) -> float:
        c = self.cells.get((minute_band(minute), score_state))
        if c is None or c.n < MIN_CELL_N:
            return self.global_mean
        return c.mean


def minute_band(minute: float) -> int:
    return sum(1 for edge in MINUTE_BANDS if minute >= edge)


def score_state(goals_for: int, goals_against: int) -> str:
    if goals_for > goals_against:
        return "leading"
    if goals_for < goals_against:
        return "trailing"
    return "drawing"


def fit_state_baseline(samples: Iterable[BaselineSample]) -> StateBaseline:
    rows = list(samples)
    if not rows:
        return StateBaseline(cells={}, global_mean=0.0, samples=0)
    acc: dict[StateKey, list[float]] = {}
    for r in rows:
        acc.setdefault((minute_band(r.minute), r.score_state), []).append(r.xg_delta)
    cells = {
        k: CellStat(band=k[0], score_state=k[1], n=len(v), mean=round(sum(v) / len(v), 5))
        for k, v in acc.items()
    }
    g = sum(r.xg_delta for r in rows) / len(rows)
    return StateBaseline(cells=cells, global_mean=round(g, 5), samples=len(rows))


def adjusted_delta(baseline: StateBaseline, *, minute: float, score_state: str,
                   xg_delta: float) -> float:
    """Kararın durum-düzeltilmiş puanı: gözlenen Δ − o durumda olağan Δ."""
    return round(xg_delta - baseline.expected(minute, score_state), 5)
