"""Set-piece Routine Builder — rakibin zayıf zone'unu hedefleyen rutin önerisi.

Mantık:
1. Rakibin SAVUNDUĞU set-piece şutlarının zone heatmap'i → en zayıf zone
   (en yüksek conversion yediği)
2. Bizim SALDIRDIĞIMIZ set-piece zone heatmap'imiz → güçlü olduğumuz zone
3. İkisinin kesişimi → "Önümüzdeki korner için target: zone X, technique Y"

Bonus: rakibin pattern'inden (en sık yaptığı set-piece tipi) kaçınan
alternatif (rakip near-post ağırlıklı yapıyorsa, biz central'a yığalım).

Saf hesap. Shot listeleri (bizim ve rakip) input.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.audit import AuditRecord, EngineResult
from app.domain import Shot
from app.engine.set_piece_zones import compute_set_piece_zones

ENGINE_NAME = "engine.set_piece_routine"
ENGINE_VERSION = "1"

# Zone tipi → in-swinger / out-swinger / kısa korner önerisi
ZONE_TO_TECHNIQUE: dict[str, str] = {
    "near_post": "in_swinger",     # yakın direğe doğru kavisli
    "central_6yd": "kısa_korner",  # 6 yarda ortasına çekme
    "far_post": "out_swinger",     # uzak direğe açılan
    "penalty_arc": "kısa_pas",     # ceza yayına çıkartma
    "outside_box": "şut_için_pas",
}

ZONE_TR_LABEL: dict[str, str] = {
    "near_post": "yakın direk",
    "central_6yd": "kale ağzı (6 yd)",
    "far_post": "uzak direk",
    "penalty_arc": "ceza yayı",
    "outside_box": "ceza dışı",
}


@dataclass(frozen=True)
class RoutineRecommendation:
    target_zone: str                # önerilen hedef zone
    technique: str                  # önerilen vuruş tekniği
    rationale: str                  # human-readable Türkçe gerekçe
    opponent_weakness_score: float  # rakibin bu zone'a karşı zayıflığı (0-1)
    our_strength_score: float       # bizim bu zone'daki başarımız (0-1)
    routine_score: float            # weakness × our_strength (compounded)


@dataclass(frozen=True)
class SetPieceRoutineReport:
    my_team_external_id: int
    opponent_team_external_id: int
    set_piece_type: str             # "corner_kick" | "free_kick" | "all"
    top_recommendations: tuple[RoutineRecommendation, ...]  # top 2-3
    avoid_zone: str                 # rakibin pattern'inden — rakip burayı bekliyor
    matches_analyzed: int


def compute_set_piece_routine(
    *,
    my_team_external_id: int,
    opponent_team_external_id: int,
    my_offensive_shots: Iterable[Shot],
    opponent_defensive_shots: Iterable[Shot],   # rakibin YEDİĞİ şutlar
    opponent_offensive_shots: Iterable[Shot],   # rakibin attığı şutlar (pattern için)
    set_piece_type: str = "all",
    matches_analyzed: int = 1,
) -> EngineResult[SetPieceRoutineReport]:
    """Önümüzdeki set-piece için zone + teknik önerisi.

    Algoritma:
    1. Rakibin yediği zone'larda en çok conversion → zayıf zone listesi
    2. Bizim attığımız zone'larda en yüksek conversion → güçlü zone listesi
    3. routine_score = weakness × strength → en yüksek 2-3 öner
    4. Rakibin attığı pattern (kendi en sık zone) → "avoid" (rakip o zone'u
       bekliyor olabilir — defansif konsantrasyonu yüksek)
    """
    # Bizim ofansif zone'lar
    our_zones = compute_set_piece_zones(
        my_team_external_id, my_offensive_shots,
        role="offensive", set_piece_type=set_piece_type,
        matches_analyzed=matches_analyzed,
    ).value
    # Rakibin yediği zone'lar — defensive role
    opp_def_zones = compute_set_piece_zones(
        opponent_team_external_id, opponent_defensive_shots,
        role="defensive", set_piece_type=set_piece_type,
        matches_analyzed=matches_analyzed,
    ).value
    # Rakibin saldıran pattern (rakip bizim aleyhe set-piece kazandığında nereye atıyor)
    opp_off_zones = compute_set_piece_zones(
        opponent_team_external_id, opponent_offensive_shots,
        role="offensive", set_piece_type=set_piece_type,
        matches_analyzed=matches_analyzed,
    ).value

    # Skor: opponent weakness (yediği conversion) × our strength (kendi conversion)
    recommendations: list[RoutineRecommendation] = []
    for zone_name in ZONE_TR_LABEL:
        opp_weakness = next(
            (z.conversion_rate for z in opp_def_zones.zones if z.zone == zone_name),
            0.0,
        )
        our_strength = next(
            (z.conversion_rate for z in our_zones.zones if z.zone == zone_name),
            0.0,
        )
        # Compound score — ikisinin de yüksek olması gerek
        score = round(opp_weakness * (1 + our_strength), 4)
        if score <= 0:
            continue
        recommendations.append(RoutineRecommendation(
            target_zone=zone_name,
            technique=ZONE_TO_TECHNIQUE.get(zone_name, "regular"),
            rationale=(
                f"Rakip {ZONE_TR_LABEL[zone_name]}'da %"
                f"{int(opp_weakness * 100)} conversion yiyor; "
                f"biz aynı bölgede %{int(our_strength * 100)} skor üretiyoruz"
            ),
            opponent_weakness_score=round(opp_weakness, 3),
            our_strength_score=round(our_strength, 3),
            routine_score=score,
        ))
    recommendations.sort(key=lambda r: -r.routine_score)
    top = tuple(recommendations[:3])

    # Avoid zone — rakibin saldırgan pattern'inden
    avoid = (opp_off_zones.most_threatening_zone
             if opp_off_zones.total_shots > 0 else "insufficient_data")

    report = SetPieceRoutineReport(
        my_team_external_id=my_team_external_id,
        opponent_team_external_id=opponent_team_external_id,
        set_piece_type=set_piece_type,
        top_recommendations=top,
        avoid_zone=avoid,
        matches_analyzed=matches_analyzed,
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="team", subject_id=my_team_external_id,
        metric="set_piece_routine",
        value={
            "set_piece_type": set_piece_type,
            "matches_analyzed": matches_analyzed,
            "top_recommendations": [
                {
                    "zone": r.target_zone, "technique": r.technique,
                    "score": r.routine_score,
                    "rationale": r.rationale,
                } for r in top
            ],
            "avoid_zone": avoid,
        },
        inputs={
            "set_piece_type": set_piece_type,
            "opponent_team_external_id": opponent_team_external_id,
            "matches_analyzed": matches_analyzed,
        },
        formula=(
            "routine_score = opp_weakness × (1 + our_strength) per zone; "
            "rank desc; technique zone→technique map; avoid = opp_offensive "
            "most_threatening (rakip o zone'u bekliyor olabilir)"
        ),
    )
    return EngineResult(value=report, audit=audit)
