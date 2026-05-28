"""Match Dominance Score — bir maçtaki üstünlüğün tek bileşik skoru.

Tanım: bir takımın bir maçtaki üstünlüğünü 5 boyutta birleştirir:
- xG difference   (engine.xg)
- Field tilt difference (engine.field_tilt)
- Possession share (pasların yarısı bizim mi)
- Shots difference
- xT difference (engine.xt — Karun Singh)

Final skor: -10 .. +10. Pozitif = bizim üstünlüğümüz. ±2 = denge.

Saf hesap; engine.xg.compute_shot_xg ve engine.xt.compute_team_xt çağırır.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.audit import AuditRecord, EngineResult
from app.domain import Carry, PassEvent, Shot
from app.engine.field_tilt import compute_field_tilt
from app.engine.xg import compute_shot_xg
from app.engine.xt import compute_team_xt

ENGINE_NAME = "engine.match_dominance"
ENGINE_VERSION = "1"


@dataclass(frozen=True)
class MatchDominanceReport:
    team_external_id: int
    opponent_team_external_id: int
    xg_diff: float
    field_tilt_team_share: float    # 0-1
    possession_share: float         # 0-1
    shots_diff: int
    xt_diff: float
    dominance_score: float          # -10..+10
    label: str                      # "dominant" | "balanced" | "dominated"


def _label(score: float) -> str:
    if score >= 2.0:
        return "dominant"
    if score <= -2.0:
        return "dominated"
    return "balanced"


def _team_shots(shots: Iterable[Shot], team_id: int,
                all_passes: list[PassEvent]) -> list[Shot]:
    """Shot domain'inde team_external_id yok; aynı dakikada o takımdan pas
    olduğuna bakarak heuristic eşleştirme yapamayız (gürültülü). Caller
    önceden filtre etmiş varsay; biz aldığımız listeyi olduğu gibi kullanıyoruz.
    """
    return list(shots)


def compute_match_dominance(
    *,
    team_external_id: int,
    opponent_team_external_id: int,
    team_shots: Iterable[Shot],
    opponent_shots: Iterable[Shot],
    all_passes: Iterable[PassEvent],
    team_carries: Iterable[Carry] = (),
    opponent_carries: Iterable[Carry] = (),
) -> EngineResult[MatchDominanceReport]:
    """Bir maçtaki tek-takımın üstünlüğü.

    Shot'lar caller tarafından takım filtresinden geçmiş olarak gelir
    (Shot domain'inde team_external_id yok).
    """
    passes = list(all_passes)
    ts = list(team_shots)
    os_ = list(opponent_shots)

    # xG farkı
    team_xg = sum(compute_shot_xg(s, mode="geometric").value.xg for s in ts)
    opp_xg = sum(compute_shot_xg(s, mode="geometric").value.xg for s in os_)
    xg_diff = team_xg - opp_xg

    # Field tilt (zaten 0-1 share verir)
    ft = compute_field_tilt(team_external_id, opponent_team_external_id, passes).value
    ft_share = ft.team_a_tilt

    # Possession share — pas sayısı oranı
    team_pass = sum(1 for p in passes if p.team_external_id == team_external_id)
    opp_pass = sum(1 for p in passes if p.team_external_id == opponent_team_external_id)
    total_pass = team_pass + opp_pass
    poss_share = team_pass / total_pass if total_pass else 0.5

    # Şut farkı
    shots_diff = len(ts) - len(os_)

    # xT farkı
    team_xt = compute_team_xt(team_external_id, passes, list(team_carries)).value
    opp_xt = compute_team_xt(opponent_team_external_id, passes, list(opponent_carries)).value
    xt_diff = team_xt.total_xt - opp_xt.total_xt

    # Kompozit skor (her bileşen -2..+2 normalize):
    # xg_diff clip ±3.0 → scale 0.66
    # ft_share / poss_share: 0.5 baseline; (share - 0.5) × 4 = -2..+2
    # shots_diff clip ±10 → scale 0.2
    # xt_diff clip ±3.0 → scale 0.66
    def _clip(v: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, v))

    s_xg = _clip(xg_diff, -3, 3) * (2 / 3)
    s_ft = (ft_share - 0.5) * 4
    s_poss = (poss_share - 0.5) * 4
    s_shots = _clip(shots_diff, -10, 10) * 0.2
    s_xt = _clip(xt_diff, -3, 3) * (2 / 3)
    score = round(s_xg + s_ft + s_poss + s_shots + s_xt, 2)
    score = max(-10.0, min(10.0, score))

    report = MatchDominanceReport(
        team_external_id=team_external_id,
        opponent_team_external_id=opponent_team_external_id,
        xg_diff=round(xg_diff, 3),
        field_tilt_team_share=round(ft_share, 3),
        possession_share=round(poss_share, 3),
        shots_diff=shots_diff,
        xt_diff=round(xt_diff, 3),
        dominance_score=score,
        label=_label(score),
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="team", subject_id=team_external_id,
        metric="match_dominance",
        value={
            "xg_diff": report.xg_diff,
            "field_tilt_team_share": report.field_tilt_team_share,
            "possession_share": report.possession_share,
            "shots_diff": report.shots_diff,
            "xt_diff": report.xt_diff,
            "dominance_score": score,
            "label": report.label,
        },
        inputs={
            "components": ["xg_diff", "field_tilt", "possession", "shots_diff", "xt_diff"],
            "opponent_team_external_id": opponent_team_external_id,
        },
        formula="weighted sum: xg_diff(2/3) + (ft-0.5)*4 + (poss-0.5)*4 + shots*0.2 + xt(2/3)",
    )
    return EngineResult(value=report, audit=audit)
