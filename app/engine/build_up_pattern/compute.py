"""Build-up pattern analizi — bir takımın saldırı başlangıçları.

Possession sequence'leri possession_id ile gruplayıp:
- Başlangıç zonu (defansif/orta/hücum üçtebir)
- Pas zinciri uzunluğu
- Uzun top mu kısa pas mı
- Sequence sonucu (şut/gol/kayıp)
- Counter-attack mı (top kazandıktan <10 sn şut)

Caller possession_id-gruplanmış PassEvent listelerini geçer; engine
descriptive agregat verir.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from app.audit import AuditRecord, EngineResult
from app.domain import PassEvent, Shot

ENGINE_NAME = "engine.build_up_pattern"
ENGINE_VERSION = "1"

StartZone = Literal["defensive_third", "middle_third", "attacking_third"]

# Zone boundaries (saha 100×100 normalize, x ekseni)
DEFENSIVE_THIRD_MAX = 100.0 / 3   # x ≤ 33.33
MIDDLE_THIRD_MAX = 200.0 / 3      # 33.33 < x ≤ 66.67
LONG_BALL_DISTANCE = 35.0          # pas uzunluğu (normalize unit) ≥ 35 → uzun top


@dataclass(frozen=True)
class BuildUpReport:
    """Bir takımın N maç birleşik build-up agregat."""
    team_external_id: int
    matches_analyzed: int
    total_sequences: int
    # Sequence başlangıç zone dağılımı
    starts_in_defensive_third: int
    starts_in_middle_third: int
    starts_in_attacking_third: int
    # Pas tipleri
    long_balls_pct: float          # uzun top yüzdesi (0..1)
    short_passes_pct: float
    # Sonuçlar
    sequences_ended_with_shot: int
    sequences_ended_with_goal: int
    counter_attacks: int           # sequence < 10 sn ve şutla bitti
    # Ortalama
    avg_sequence_length: float     # ortalama pas sayısı per possession
    avg_progression_meters: float  # ortalama ileri ilerleme (normalize unit)


def _zone_for_x(x: float) -> StartZone:
    if x <= DEFENSIVE_THIRD_MAX:
        return "defensive_third"
    if x <= MIDDLE_THIRD_MAX:
        return "middle_third"
    return "attacking_third"


def _pass_distance(p: PassEvent) -> float:
    """Pas uzunluğu — start ile end koordinatları arasındaki Öklid mesafesi."""
    return ((p.end_x - p.start_x) ** 2 + (p.end_y - p.start_y) ** 2) ** 0.5


def compute_build_up_pattern(
    team_external_id: int,
    passes: Iterable[PassEvent],
    shots: Iterable[Shot],
    *,
    matches_analyzed: int = 1,
) -> EngineResult[BuildUpReport]:
    """Bir takım için build-up pattern agregat.

    Algorithm:
    1. passes'i possession_id'ye göre grupla
    2. Her possession için: başlangıç zone, sequence length, pas tipleri
    3. Shots'ı possession_id ile match → sequence sonucu (şut/gol)
    4. Counter-attack: sequence < 10 sn (caller bilmesi zor; tahmin: pas başına 5 sn)
    """
    pass_list = [p for p in passes if p.team_external_id == team_external_id]

    # Possession groupings (possession_id → pass list)
    by_possession: dict[int, list[PassEvent]] = {}
    for p in pass_list:
        if p.possession_id is None:
            continue
        by_possession.setdefault(p.possession_id, []).append(p)

    # Shot eşleştirme: shot.match_external_id + shot.minute ile possession bul
    # Basitleştirme: shot var mı yok mu sequence-level (proper match için
    # event.possession_id shot domain'de olmalı, şu an yok)
    shot_minute_by_match: dict[int, list[float]] = {}
    for s in shots:
        shot_minute_by_match.setdefault(s.match_external_id, []).append(s.minute)
    for m_id in shot_minute_by_match:
        shot_minute_by_match[m_id].sort()

    starts_def = starts_mid = starts_att = 0
    long_balls = 0
    short_passes = 0
    ended_shot = 0
    ended_goal = 0
    counter_attacks = 0
    total_length_sum = 0
    progression_sum = 0.0

    for _poss_id, ps in by_possession.items():
        if not ps:
            continue
        sorted_ps = sorted(ps, key=lambda x: (x.period, x.minute))
        first = sorted_ps[0]
        last = sorted_ps[-1]
        # Start zone
        zone = _zone_for_x(first.start_x)
        if zone == "defensive_third":
            starts_def += 1
        elif zone == "middle_third":
            starts_mid += 1
        else:
            starts_att += 1
        # Pas tipleri
        for p in sorted_ps:
            if _pass_distance(p) >= LONG_BALL_DISTANCE:
                long_balls += 1
            else:
                short_passes += 1
        # Sequence length + progression
        total_length_sum += len(sorted_ps)
        progression_sum += max(0.0, last.end_x - first.start_x)
        # Sequence < 30 sn (ham proxy: ilk pas + son pas minute farkı)
        duration_min = last.minute - first.minute
        # Şut eşleştirme — son pas + 10 sn içinde aynı maçta şut var mı
        match_id = first.match_external_id
        shots_in_match = shot_minute_by_match.get(match_id, [])
        ended_with_shot_this_seq = any(
            last.minute <= sm <= last.minute + 0.5  # 30 sn pencere
            for sm in shots_in_match
        )
        if ended_with_shot_this_seq:
            ended_shot += 1
            if duration_min < 0.5:  # <30 sn — counter
                counter_attacks += 1

    total_sequences = len(by_possession)
    total_passes = long_balls + short_passes
    long_pct = long_balls / total_passes if total_passes > 0 else 0.0
    short_pct = 1.0 - long_pct if total_passes > 0 else 0.0
    avg_seq_len = total_length_sum / total_sequences if total_sequences > 0 else 0.0
    avg_progression = progression_sum / total_sequences if total_sequences > 0 else 0.0

    report = BuildUpReport(
        team_external_id=team_external_id,
        matches_analyzed=matches_analyzed,
        total_sequences=total_sequences,
        starts_in_defensive_third=starts_def,
        starts_in_middle_third=starts_mid,
        starts_in_attacking_third=starts_att,
        long_balls_pct=round(long_pct, 4),
        short_passes_pct=round(short_pct, 4),
        sequences_ended_with_shot=ended_shot,
        sequences_ended_with_goal=ended_goal,
        counter_attacks=counter_attacks,
        avg_sequence_length=round(avg_seq_len, 2),
        avg_progression_meters=round(avg_progression, 2),
    )
    audit = AuditRecord(
        engine=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        subject_type="team",
        subject_id=team_external_id,
        metric="build_up_pattern",
        value={
            "total_sequences": total_sequences,
            "starts_def": starts_def,
            "starts_mid": starts_mid,
            "starts_att": starts_att,
            "long_balls_pct": report.long_balls_pct,
            "ended_shot": ended_shot,
            "counter_attacks": counter_attacks,
            "avg_seq_length": report.avg_sequence_length,
            "avg_progression": report.avg_progression_meters,
            "matches": matches_analyzed,
        },
        inputs={
            "long_ball_distance": LONG_BALL_DISTANCE,
            "defensive_third_max": DEFENSIVE_THIRD_MAX,
            "middle_third_max": MIDDLE_THIRD_MAX,
        },
        formula=(
            "possession_id grouping; start zone by first pass start_x; "
            "long_ball if pass distance ≥ 35; counter_attack if sequence < 30s + shot"
        ),
    )
    return EngineResult(value=report, audit=audit)
