"""Set-piece Pattern History — rakibin geçmiş set-piece tercihleri.

Tanım: bir takımın (rakip) son N maçtaki set-piece şutlarını analiz et:
- En sık atılan zone (set_piece_zones engine'inin tarihsel ortalaması)
- En tehlikeli zone (en yüksek conversion)
- Pattern direction (sol/orta/sağ giriş ağırlığı)
- "Pattern alert" string: maçta o rakip korner kazandığında ekrana yazılır

Canlı maç senaryosu:
- Maç başlamadan önce çağırılır, sonuç cache'lenir
- Maç sırasında rakip korner kazandığında frontend bu pattern'i gösterir

Pure-compute; engine.set_piece_zones'i N maç birleşimine uygular.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.audit import AuditRecord, EngineResult
from app.domain import Shot
from app.engine.set_piece_zones import compute_set_piece_zones

ENGINE_NAME = "engine.set_piece_pattern_history"
ENGINE_VERSION = "1"


@dataclass(frozen=True)
class SetPiecePatternHistoryReport:
    team_external_id: int
    matches_analyzed: int
    total_set_piece_shots: int
    total_set_piece_goals: int
    most_frequent_zone: str         # en çok şut o zone'a gitti
    most_dangerous_zone: str        # en yüksek conversion
    zone_frequencies: dict[str, int]   # zone → şut sayısı
    zone_conversions: dict[str, float]  # zone → goal_conversion
    alert_text: str                  # canlı maçta gösterilecek metin


def compute_set_piece_pattern_history(
    team_external_id: int,
    all_shots: Iterable[Shot],
    *,
    matches_analyzed: int = 1,
) -> EngineResult[SetPiecePatternHistoryReport]:
    """N maçlık set-piece şutu üzerinden rakip pattern'i.

    `all_shots` caller tarafında birden çok maçtan birleştirilmiş gelir
    (filter: pattern in {corner_kick, free_kick, set_piece}).
    """
    # Aynı set_piece_zones engine'ini topluluk üstüne uygula
    zone_result = compute_set_piece_zones(
        team_external_id, all_shots,
        role="offensive", set_piece_type="all",
        matches_analyzed=matches_analyzed,
    ).value

    zone_freqs = {z.zone: z.shots for z in zone_result.zones}
    zone_convs = {z.zone: z.conversion_rate for z in zone_result.zones}
    # En sık (frequency)
    most_freq = max(zone_freqs, key=lambda k: zone_freqs[k]) \
        if zone_result.total_shots else "insufficient_data"
    # En tehlikeli (conversion); eşit varsa en çok şut
    if zone_result.total_shots:
        most_dang = max(zone_freqs, key=lambda k: (
            zone_convs[k], zone_freqs[k],
        ))
    else:
        most_dang = "insufficient_data"

    # Alert text — Türkçe doğal cümle
    zone_tr = {
        "near_post": "yakın direk", "central_6yd": "kale ağzı (6 yd)",
        "far_post": "uzak direk", "penalty_arc": "ceza yayı",
        "outside_box": "ceza dışı",
    }
    if zone_result.total_shots == 0:
        alert = "Yeterli set-piece veri yok"
    else:
        n_shots = zone_freqs.get(most_freq, 0)
        alert = (
            f"Son {matches_analyzed} maçta {zone_result.total_shots} set-piece "
            f"şutunun {n_shots}'ı {zone_tr.get(most_freq, most_freq)}'na gitti; "
            f"en tehlikelisi {zone_tr.get(most_dang, most_dang)} "
            f"(%{int(zone_convs.get(most_dang, 0) * 100)} gol)"
        )

    report = SetPiecePatternHistoryReport(
        team_external_id=team_external_id,
        matches_analyzed=matches_analyzed,
        total_set_piece_shots=zone_result.total_shots,
        total_set_piece_goals=zone_result.total_goals,
        most_frequent_zone=most_freq,
        most_dangerous_zone=most_dang,
        zone_frequencies=zone_freqs,
        zone_conversions=zone_convs,
        alert_text=alert,
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="team", subject_id=team_external_id,
        metric="set_piece_pattern_history",
        value={
            "matches_analyzed": matches_analyzed,
            "total_shots": zone_result.total_shots,
            "total_goals": zone_result.total_goals,
            "most_frequent_zone": most_freq,
            "most_dangerous_zone": most_dang,
            "alert_text": alert,
        },
        inputs={"matches_analyzed": matches_analyzed},
        formula="aggregate set_piece_zones over N matches; pick most_frequent and most_dangerous",
    )
    return EngineResult(value=report, audit=audit)
