"""Opponent Weakness — rakibin zayıf kanal/zone tespiti.

Tanım: rakibin SAVUNMA bölgesinde (kendi yarımıza yakın) bizim takımın
**girişlerinin** (pas/carry final third'a) hangi kanaldan en yoğun
yapıldığını + rakibin defansif aksiyon yoğunluğunun düşük olduğu kanalı
çıkarır.

İkisi birleşince: "bizim bu kanaldan top alıp giriyoruz + rakibin
defansif yoğunluğu bu kanalda düşük" → exploit edilebilir zayıflık.

Kanallar:
- left:    y < 33.3
- central: 33.3 ≤ y ≤ 66.7
- right:   y > 66.7

Çıktı: en savunmasız kanal + ranking; agent'ın "şu kanattan içeri girin"
diye somut tavsiye verebilmesi için.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.audit import AuditRecord, ConfidenceInfo, EngineResult
from app.domain import Carry, DefensiveAction, PassEvent
from app.engine.confidence import score_confidence

ENGINE_NAME = "engine.opponent_weakness"
ENGINE_VERSION = "1"

FINAL_THIRD_X = 66.7
LEFT_Y_MAX = 33.3
RIGHT_Y_MIN = 66.7


def _channel(y: float) -> str:
    if y < LEFT_Y_MAX:
        return "left"
    if y > RIGHT_Y_MIN:
        return "right"
    return "central"


@dataclass(frozen=True)
class ChannelVulnerability:
    channel: str
    our_attacks: int            # bu kanaldan yaptığımız final-third girişleri
    opp_def_actions: int        # rakibin bu kanaldaki savunma aksiyonu
    vulnerability_score: float  # (our_attacks + 1) / (opp_def_actions + 1)


@dataclass(frozen=True)
class OpponentWeaknessReport:
    my_team_external_id: int
    opponent_team_external_id: int
    by_channel: tuple[ChannelVulnerability, ...]
    most_vulnerable_channel: str
    recommendation: str             # human-readable kısa öneri


def compute_opponent_weakness(
    *,
    my_team_external_id: int,
    opponent_team_external_id: int,
    all_passes: Iterable[PassEvent],
    all_carries: Iterable[Carry],
    all_def_actions: Iterable[DefensiveAction],
) -> EngineResult[OpponentWeaknessReport]:
    """Rakip savunmasında en zayıf kanalı bul.

    Algoritma:
    1. Bizim final-third'a giren pas+carry'leri (start_x<66.7, end_x≥66.7)
       end_y kanalına göre say
    2. Rakibin defansif aksiyonlarını kanal başına say
    3. Vulnerability = our_attacks / opp_def_actions (smoothing +1)
    4. En yüksek score = en zayıf kanal
    """
    our_attacks = {"left": 0, "central": 0, "right": 0}
    for p in all_passes:
        if p.team_external_id != my_team_external_id:
            continue
        if p.start_x >= FINAL_THIRD_X or p.end_x < FINAL_THIRD_X:
            continue
        our_attacks[_channel(p.end_y)] += 1
    for c in all_carries:
        if c.team_external_id != my_team_external_id:
            continue
        if c.start_x >= FINAL_THIRD_X or c.end_x < FINAL_THIRD_X:
            continue
        our_attacks[_channel(c.end_y)] += 1

    opp_defs = {"left": 0, "central": 0, "right": 0}
    for d in all_def_actions:
        if d.team_external_id != opponent_team_external_id:
            continue
        # Rakibin kendi savunma yarısı: x ≤ 33.3 (kendi kalesi yakını)
        # Not: x rakibin perspektifinden farklı; biz toplam y dağılımına bakıyoruz
        opp_defs[_channel(d.y)] += 1

    by_channel: list[ChannelVulnerability] = []
    for ch in ("left", "central", "right"):
        score = (our_attacks[ch] + 1) / (opp_defs[ch] + 1)
        by_channel.append(ChannelVulnerability(
            channel=ch,
            our_attacks=our_attacks[ch],
            opp_def_actions=opp_defs[ch],
            vulnerability_score=round(score, 3),
        ))
    sorted_v = sorted(by_channel, key=lambda v: -v.vulnerability_score)
    most_vuln = sorted_v[0].channel if sorted_v else "central"

    # Recommendation
    total_our = sum(our_attacks.values())
    if total_our == 0:
        rec = "Yeterli veri yok (saldırı azlığı)"
    else:
        side_tr = {"left": "sol kanat", "central": "merkez", "right": "sağ kanat"}
        rec = (
            f"{side_tr[most_vuln]}tan ataklarımız rakibin defansif "
            f"aksiyonundan {sorted_v[0].vulnerability_score:.2f}× yoğun; "
            f"2. yarıda bu kanadı zorlayın"
        )

    report = OpponentWeaknessReport(
        my_team_external_id=my_team_external_id,
        opponent_team_external_id=opponent_team_external_id,
        by_channel=tuple(by_channel),
        most_vulnerable_channel=most_vuln,
        recommendation=rec,
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="match", subject_id=0,
        metric="opponent_weakness",
        value={
            "most_vulnerable_channel": most_vuln,
            "by_channel": [
                {"channel": c.channel, "our_attacks": c.our_attacks,
                 "opp_def_actions": c.opp_def_actions,
                 "vulnerability_score": c.vulnerability_score}
                for c in by_channel
            ],
        },
        inputs={
            "final_third_x": FINAL_THIRD_X,
            "left_y_max": LEFT_Y_MAX,
            "right_y_min": RIGHT_Y_MIN,
        },
        formula="vulnerability = (our_attacks+1) / (opp_def_actions+1) per channel",
    )
    # Güven: sample_size = final-third atak + rakip def aksiyon toplamı;
    # magnitude = en zayıf kanalın 1.0 nötrden sapması (|score-1|).
    _vuln_top = sorted_v[0].vulnerability_score if sorted_v else 1.0
    conf = score_confidence(
        sample_size=sum(c.our_attacks + c.opp_def_actions for c in by_channel),
        magnitude=min(1.0, abs(_vuln_top - 1.0)),
    )
    return EngineResult(
        value=report, audit=audit,
        confidence=ConfidenceInfo(conf.score, conf.label, conf.drivers),
    )
