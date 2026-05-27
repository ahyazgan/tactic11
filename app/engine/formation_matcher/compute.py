"""Tactical formation matcher — formasyon A vs formasyon B tarihsel agregat.

Use case: "Rakip 4-3-3 oynayacak; biz 3-5-2 ile çıkarsak ne olur?"
Geçmiş maçlardan formation_played × formation_played karşılaşmaları topla:
- Win/draw/loss
- Ortalama gol farkı
- Total maç sayısı

DİKKAT: Bu engine 'descriptive' (betimsel) — küçük örneklemden 'predictive'
çıkarım yapmıyor. Brief'lerde "son 38 benzer maçta %58 win rate" gibi
açıklamalar bu engine'in çıktısı.

Veri kaynağı: player_appearances.formation_played (Prompt 4 ile eklenen kolon
+ her oyuncuya kopyalandı; bir maçtaki bir takım için tek formasyon — herhangi
bir oyuncunun formation_played'ini alırız).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass

from app.audit import AuditRecord, EngineResult

ENGINE_NAME = "engine.formation_matcher"
ENGINE_VERSION = "1"


@dataclass(frozen=True)
class FormationMatchupRecord:
    """Bir geçmiş maçın formation perspektifinden özet."""
    match_external_id: int
    my_formation: str
    opp_formation: str
    my_goals: int
    opp_goals: int

    @property
    def outcome(self) -> str:
        if self.my_goals > self.opp_goals:
            return "win"
        if self.my_goals < self.opp_goals:
            return "loss"
        return "draw"


@dataclass(frozen=True)
class FormationMatchupReport:
    """Bir formation çiftinin (my, opp) tarihsel performansı."""
    my_formation: str
    opp_formation: str
    matches_played: int
    wins: int
    draws: int
    losses: int
    win_rate: float        # 0..1
    avg_goal_diff: float   # my - opp ortalama
    avg_my_goals: float
    avg_opp_goals: float


def compute_formation_matchup(
    my_formation: str,
    opp_formation: str,
    records: Iterable[FormationMatchupRecord],
) -> EngineResult[FormationMatchupReport]:
    """Bir (my, opp) formation çifti için tarihsel agregat hesapla."""
    relevant = [
        r for r in records
        if r.my_formation == my_formation and r.opp_formation == opp_formation
    ]
    n = len(relevant)
    if n == 0:
        report = FormationMatchupReport(
            my_formation=my_formation, opp_formation=opp_formation,
            matches_played=0, wins=0, draws=0, losses=0,
            win_rate=0.0, avg_goal_diff=0.0,
            avg_my_goals=0.0, avg_opp_goals=0.0,
        )
    else:
        outcomes = [r.outcome for r in relevant]
        wins = outcomes.count("win")
        draws = outcomes.count("draw")
        losses = outcomes.count("loss")
        my_goals_sum = sum(r.my_goals for r in relevant)
        opp_goals_sum = sum(r.opp_goals for r in relevant)
        report = FormationMatchupReport(
            my_formation=my_formation, opp_formation=opp_formation,
            matches_played=n, wins=wins, draws=draws, losses=losses,
            win_rate=round(wins / n, 4),
            avg_goal_diff=round((my_goals_sum - opp_goals_sum) / n, 3),
            avg_my_goals=round(my_goals_sum / n, 3),
            avg_opp_goals=round(opp_goals_sum / n, 3),
        )
    audit = AuditRecord(
        engine=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        subject_type="formation",
        subject_id=0,  # formation çiftinin tek bir int'i yok
        metric="formation_matchup",
        value=asdict(report),
        inputs={
            "my_formation": my_formation, "opp_formation": opp_formation,
            "records_considered": n,
        },
        formula=(
            "matches where (my_formation, opp_formation) match; "
            "wins/draws/losses + avg(my - opp goals)"
        ),
    )
    return EngineResult(value=report, audit=audit)


def best_formations_against(
    opp_formation: str,
    records: Iterable[FormationMatchupRecord],
    *,
    min_matches: int = 3,
    top_n: int = 5,
) -> list[FormationMatchupReport]:
    """Belirli bir rakip formasyona karşı en iyi N formasyonu sırala.

    `min_matches` altında çift atlanır (sample size guard). Sıralama:
    win_rate desc, ikincil avg_goal_diff desc.
    """
    record_list = list(records)
    my_formations = {r.my_formation for r in record_list if r.opp_formation == opp_formation}
    reports: list[FormationMatchupReport] = []
    for my_form in my_formations:
        rep = compute_formation_matchup(my_form, opp_formation, record_list).value
        if rep.matches_played >= min_matches:
            reports.append(rep)
    reports.sort(key=lambda r: (r.win_rate, r.avg_goal_diff), reverse=True)
    return reports[:top_n]
