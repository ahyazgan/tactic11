"""Coaching Identity Vector — koçun taktiksel parmak izi.

Bir takımın N maçlık örnekleminden, koçun taktiksel kimliğini 8 boyutlu
bir vektöre indirger:

1. press_intensity    — engine.ppda (düşük = yoğun pres → 1/(1+ppda/10))
2. defensive_line     — engine.defensive_line (avg_x / 100)
3. compactness        — engine.compactness (1 - overall_stdev/40)
4. transition_speed   — engine.transition (fast_counter_ratio)
5. directness         — engine.direct_play (avg_directness)
6. tempo              — engine.tempo (passes_per_minute / 15)
7. attacking_third_recovery — engine.recovery_zone_heat (attacking_share)
8. channel_balance    — engine.channel_preference (1 - max_share)

Sonuç: 8-vektör + benzer koç etiketi (kural-bazlı 5 arketip):
- "high_press_possession"  (Pep, Klopp, Luis Enrique)
- "low_block_counter"      (Mourinho v2, Simeone)
- "direct_vertical"        (Bielsa, Nagelsmann)
- "balanced_pragmatic"     (Ancelotti, Tuchel)
- "deep_organised"         (Mancini, Allegri)

Saf composit; aşağı engine'lere temiz delege.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.audit import AuditRecord, EngineResult
from app.domain import DefensiveAction, PassEvent
from app.engine.channel_preference import compute_channel_preference
from app.engine.compactness import compute_compactness
from app.engine.defensive_line import compute_defensive_line
from app.engine.direct_play import compute_direct_play
from app.engine.ppda import compute_ppda
from app.engine.recovery_zone_heat import compute_recovery_zone_heat
from app.engine.tempo import compute_tempo
from app.engine.transition import compute_transition

ENGINE_NAME = "engine.coaching_identity"
ENGINE_VERSION = "1"


@dataclass(frozen=True)
class CoachingIdentityVector:
    press_intensity: float
    defensive_line: float
    compactness: float
    transition_speed: float
    directness: float
    tempo: float
    attacking_third_recovery: float
    channel_balance: float


@dataclass(frozen=True)
class CoachingIdentityReport:
    team_external_id: int
    matches_analyzed: int
    vector: CoachingIdentityVector
    archetype: str
    # Üst-2 en yüksek özellik ve etiketi
    top_features: tuple[str, ...]


def _classify_archetype(v: CoachingIdentityVector) -> str:
    """Rule-based: 5 arketipin biri.

    Sıra önemli (kombinasyonlar üst üste binmesin).
    """
    # 1. high_press_possession: press high + tempo high
    if v.press_intensity >= 0.55 and v.tempo >= 0.45:
        return "high_press_possession"
    # 2. direct_vertical: directness high + transition fast
    if v.directness >= 0.50 and v.transition_speed >= 0.25:
        return "direct_vertical"
    # 3. low_block_counter: defensive_line low + transition fast
    if v.defensive_line <= 0.35 and v.transition_speed >= 0.25:
        return "low_block_counter"
    # 4. deep_organised: defensive_line low + compactness high
    if v.defensive_line <= 0.40 and v.compactness >= 0.50:
        return "deep_organised"
    # 5. default
    return "balanced_pragmatic"


def compute_coaching_identity(
    team_external_id: int,
    opponent_team_external_id: int,
    all_passes: Iterable[PassEvent],
    all_def_actions: Iterable[DefensiveAction],
    all_shots: Iterable,
    *,
    matches_analyzed: int = 1,
) -> EngineResult[CoachingIdentityReport]:
    """Koçun 5-10 maçlık örnekleminden 8-boyutlu kimlik vektörü.

    Saf composit — aşağıdaki engine'lerin çıktısını normalize edip birleştirir.
    """
    passes = list(all_passes)
    defs = list(all_def_actions)
    shots = list(all_shots)

    ppda = compute_ppda(team_external_id, passes, defs,
                        matches_analyzed=matches_analyzed).value
    line = compute_defensive_line(team_external_id, defs,
                                   matches_analyzed=matches_analyzed).value
    compact = compute_compactness(team_external_id, passes, defs,
                                   matches_analyzed=matches_analyzed).value
    trans = compute_transition(team_external_id, defs, shots,
                                matches_analyzed=matches_analyzed).value
    direct = compute_direct_play(team_external_id, passes,
                                  matches_analyzed=matches_analyzed).value
    tempo = compute_tempo(team_external_id, passes,
                           matches_analyzed=matches_analyzed).value
    rzh = compute_recovery_zone_heat(team_external_id, defs,
                                      matches_analyzed=matches_analyzed).value
    chan = compute_channel_preference(team_external_id, passes,
                                       matches_analyzed=matches_analyzed).value

    # Normalize 0-1
    # Press intensity: 1/(1+ppda/10); PPDA 8 → 0.55, PPDA 15 → 0.40, PPDA 5 → 0.67
    press_norm = 1.0 / (1.0 + max(0.0, ppda.ppda) / 10.0) if ppda.ppda < 100 else 0.0
    line_norm = min(1.0, line.avg_x / 100.0) if line.actions_counted else 0.0
    # Compactness: stdev 0-40 aralığında; küçük stdev → kompakt = yüksek skor
    compact_norm = max(0.0, 1.0 - compact.overall_stdev / 40.0) if compact.overall_stdev else 0.0
    trans_norm = trans.fast_counter_ratio
    direct_norm = direct.avg_directness
    tempo_norm = min(1.0, tempo.passes_per_minute / 15.0)
    rzh_norm = rzh.attacking_share
    # channel_balance: max share ne kadar dengeli → 1 - max(left,central,right)
    max_share = max(chan.left_share, chan.central_share, chan.right_share)
    chan_norm = max(0.0, 1.0 - max_share) if max_share else 0.0

    vec = CoachingIdentityVector(
        press_intensity=round(press_norm, 3),
        defensive_line=round(line_norm, 3),
        compactness=round(compact_norm, 3),
        transition_speed=round(trans_norm, 3),
        directness=round(direct_norm, 3),
        tempo=round(tempo_norm, 3),
        attacking_third_recovery=round(rzh_norm, 3),
        channel_balance=round(chan_norm, 3),
    )

    archetype = _classify_archetype(vec)
    # Top 2 feature
    vector_dict = {
        "press_intensity": vec.press_intensity,
        "defensive_line": vec.defensive_line,
        "compactness": vec.compactness,
        "transition_speed": vec.transition_speed,
        "directness": vec.directness,
        "tempo": vec.tempo,
        "attacking_third_recovery": vec.attacking_third_recovery,
        "channel_balance": vec.channel_balance,
    }
    top = tuple(sorted(vector_dict, key=lambda k: vector_dict[k], reverse=True)[:2])

    report = CoachingIdentityReport(
        team_external_id=team_external_id,
        matches_analyzed=matches_analyzed,
        vector=vec,
        archetype=archetype,
        top_features=top,
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="team", subject_id=team_external_id,
        metric="coaching_identity",
        value={
            "vector": vector_dict,
            "archetype": archetype,
            "top_features": list(top),
        },
        inputs={
            "matches_analyzed": matches_analyzed,
            "component_engines": [
                "ppda", "defensive_line", "compactness", "transition",
                "direct_play", "tempo", "recovery_zone_heat", "channel_preference",
            ],
        },
        formula="8-dim normalized vector across component engines; rule-based archetype",
    )
    return EngineResult(value=report, audit=audit)
