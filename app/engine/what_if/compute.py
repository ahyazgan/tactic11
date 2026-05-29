"""What-If — karşı-olgu (counterfactual) senaryo simülatörü (saf).

"X oyuncuyu çıkarırsam takım çıktısı (xT/dominance/gol farkı proxy) nasıl
değişir?" Saf, açıklanabilir bir tahmin: oyuncunun takım metriğine katkısını
çıkar, yerine gelenin beklenen katkısını ekle. Kesin tahmin DEĞİL — karar
desteği; belirsizlik raporda işaretli.

Saf: oyuncu katkı listesi + senaryo → projeksiyon. DB/ML yok.
"""
from __future__ import annotations

from dataclasses import dataclass, field

ENGINE_NAME = "engine.what_if"
ENGINE_VERSION = "1"


@dataclass(frozen=True)
class PlayerContribution:
    player_external_id: int
    # Oyuncunun takım metriğine MUTLAK katkısı (ör. xT katkısı). Toplamları ≈
    # baseline_team_metric olmalı (caller normalize eder).
    contribution: float


@dataclass(frozen=True)
class WhatIfResult:
    removed_player_id: int
    baseline_metric: float
    projected_metric: float
    delta: float                  # projected - baseline (negatif = kötüleşme)
    replacement_contribution: float
    note: str
    caveat: str = (
        "Lineer katkı varsayımı — etkileşim/şekil etkileri modellenmiyor; "
        "karar desteği, kesin tahmin değil."
    )


def simulate_removal(
    *,
    baseline_team_metric: float,
    contributions: list[PlayerContribution],
    remove_player_id: int,
    replacement_contribution: float = 0.0,
) -> WhatIfResult:
    """Bir oyuncuyu çıkar (+ opsiyonel yedek katkısı) → takım metriği projeksiyonu."""
    removed = next(
        (c for c in contributions if c.player_external_id == remove_player_id),
        None,
    )
    removed_value = removed.contribution if removed else 0.0
    projected = baseline_team_metric - removed_value + replacement_contribution
    delta = round(projected - baseline_team_metric, 3)

    if removed is None:
        note = f"#{remove_player_id} katkı listesinde yok — yalnız yedek etkisi"
    elif delta < 0:
        note = (f"#{remove_player_id} çıkarsa metrik {abs(delta):.2f} düşer "
                "(yedek bunu telafi etmiyor)")
    elif delta > 0:
        note = (f"#{remove_player_id} çıkarsa metrik {delta:.2f} artar "
                "(yedek daha verimli)")
    else:
        note = f"#{remove_player_id} çıkışı metriği değiştirmez (nötr)"

    return WhatIfResult(
        removed_player_id=remove_player_id,
        baseline_metric=round(baseline_team_metric, 3),
        projected_metric=round(projected, 3),
        delta=delta,
        replacement_contribution=round(replacement_contribution, 3),
        note=note,
    )


@dataclass(frozen=True)
class WhatIfRanking:
    safest_to_remove: int | None      # en az zarar veren oyuncu
    most_costly_to_remove: int | None  # en çok zarar veren
    results: tuple[WhatIfResult, ...] = field(default_factory=tuple)


def rank_removals(
    *,
    baseline_team_metric: float,
    contributions: list[PlayerContribution],
    replacement_contribution: float = 0.0,
) -> WhatIfRanking:
    """Her oyuncuyu tek tek çıkar → en güvenli/en maliyetli değişimi sırala."""
    results = [
        simulate_removal(
            baseline_team_metric=baseline_team_metric,
            contributions=contributions,
            remove_player_id=c.player_external_id,
            replacement_contribution=replacement_contribution,
        )
        for c in contributions
    ]
    if not results:
        return WhatIfRanking(safest_to_remove=None, most_costly_to_remove=None)
    safest = max(results, key=lambda r: r.delta)       # delta en yüksek = en az zarar
    costly = min(results, key=lambda r: r.delta)       # delta en düşük = en çok zarar
    return WhatIfRanking(
        safest_to_remove=safest.removed_player_id,
        most_costly_to_remove=costly.removed_player_id,
        results=tuple(results),
    )
