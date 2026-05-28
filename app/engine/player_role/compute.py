"""Player role typology — 8 rule-based rol etiketi.

InStat / Wyscout standart 8 rol:
1. deep_playmaker — yüksek pas, düşük şut, derin pozisyon
2. box_to_box — orta-yüksek hem hücum hem defansif aksiyon
3. defensive_mid — yüksek defansif aksiyon, düşük şut
4. inside_forward — yüksek şut, kanat → içe hareket (heat map gerek; bizde proxy)
5. wide_forward — yüksek şut + kanat
6. target_man — yüksek aerial duel + box-only pozisyon
7. ball_playing_cb — yüksek pas + defansif aksiyon
8. traditional_cb — düşük pas, yüksek aerial + defansif

Bizde tracking yok; rol tespiti per-90 stat eşiklerine dayanır (rule-based).
position_played (lineup adapter'dan) hint olarak kullanılır.

Cluster (k-means k=8) yerine rule-based — daha açıklanabilir + küçük veri ile çalışır.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from app.audit import AuditRecord, EngineResult
from app.engine._protocols import PlayerAppearanceLike

ENGINE_NAME = "engine.player_role"
ENGINE_VERSION = "1"

PlayerRole = Literal[
    "deep_playmaker",
    "box_to_box",
    "defensive_mid",
    "inside_forward",
    "wide_forward",
    "target_man",
    "ball_playing_cb",
    "traditional_cb",
    "goalkeeper",
    "unknown",
]


@dataclass(frozen=True)
class PlayerRoleReport:
    player_external_id: int
    primary_role: PlayerRole
    confidence: float  # 0..1 — kural eşiklerine ne kadar yakın
    secondary_role: PlayerRole  # ikincil rol (multi-role oyuncular için)
    inputs: dict[str, float]   # özet stat vektörü


def _aggregate_per_90(
    player_id: int,
    appearances: Iterable[PlayerAppearanceLike],
) -> dict[str, float | str]:
    """Per-90 normalize stat vektörü (player_appearances'tan).

    Mixed-type dict: float değerler + position_code string. Caller
    isinstance kontrolü ile ayırır.
    """
    apps = [a for a in appearances if a.player_external_id == player_id]
    total_min = sum(a.minutes for a in apps)
    if total_min == 0:
        return {}

    def _sum(attr: str) -> float:
        return float(sum((getattr(a, attr, None) or 0) for a in apps))

    # Position hint — son maçtaki position_played
    position = ""
    for a in apps:
        pos = getattr(a, "position_played", None)
        if pos:
            position = str(pos)
            break

    per_90 = 90.0 / total_min
    # passes_accuracy minute-weighted avg
    weight_sum = 0.0
    acc_weighted = 0.0
    for a in apps:
        acc = getattr(a, "passes_accuracy", None)
        if acc is not None and a.minutes > 0:
            acc_weighted += float(acc) * a.minutes
            weight_sum += a.minutes

    return {
        "total_minutes": float(total_min),
        "matches": float(len(apps)),
        "passes_per_90": _sum("passes_total") * per_90,
        "passes_accuracy_avg": acc_weighted / weight_sum if weight_sum > 0 else 0.0,
        "shots_per_90": _sum("shots_total") * per_90,
        "dribbles_success_per_90": _sum("dribbles_success") * per_90,
        "fouls_committed_per_90": _sum("fouls_committed") * per_90,
        "fouls_drawn_per_90": _sum("fouls_drawn") * per_90,
        "position_code": position,
    }


def _classify_role(stats: dict[str, float | str]) -> tuple[PlayerRole, float, PlayerRole]:
    """Rule-based rol sınıflandırma.

    Returns (primary_role, confidence_0_1, secondary_role).
    """
    if not stats:
        return ("unknown", 0.0, "unknown")

    pos = str(stats.get("position_code", "")).upper()

    # GK
    if pos == "G":
        return ("goalkeeper", 1.0, "unknown")

    passes = float(stats["passes_per_90"])
    acc = float(stats["passes_accuracy_avg"])
    shots = float(stats["shots_per_90"])
    dribbles = float(stats["dribbles_success_per_90"])
    fouls_comm = float(stats["fouls_committed_per_90"])
    fouls_drawn = float(stats["fouls_drawn_per_90"])

    # CB kategorisi (D pozisyon + düşük şut)
    if pos == "D" and shots < 1.0:
        # Ball-playing CB: yüksek pas + iyi accuracy
        if passes >= 55 and acc >= 88:
            return ("ball_playing_cb", 0.85, "traditional_cb")
        return ("traditional_cb", 0.85, "ball_playing_cb")

    # Forward (F pozisyon)
    if pos == "F":
        # Target man: yüksek fouls_drawn (head duel proxy) + düşük dribble
        if fouls_drawn >= 3 and dribbles < 1.5:
            return ("target_man", 0.7, "wide_forward")
        # Inside vs wide — wide_forward varsayım (tracking olmadan ayırt etmek zor)
        if dribbles >= 2:
            return ("inside_forward", 0.7, "wide_forward")
        return ("wide_forward", 0.7, "inside_forward")

    # Midfielder (M pozisyon)
    if pos == "M":
        # Defensive mid: düşük şut + yüksek defansif eğilim (fouls_committed proxy)
        if shots < 0.5 and fouls_comm >= 1.5:
            return ("defensive_mid", 0.75, "box_to_box")
        # Deep playmaker: yüksek pas + yüksek accuracy + düşük şut
        if passes >= 50 and acc >= 85 and shots < 1.5:
            return ("deep_playmaker", 0.8, "box_to_box")
        # Box-to-box: orta hücum + orta defansif
        return ("box_to_box", 0.7, "deep_playmaker")

    # Position bilinmiyor — istatistiklere göre tahmin
    if shots >= 2:
        return ("wide_forward", 0.5, "inside_forward")
    if passes >= 50 and acc >= 85:
        return ("deep_playmaker", 0.5, "box_to_box")
    return ("unknown", 0.0, "unknown")


def compute_player_role(
    player_external_id: int,
    appearances: Iterable[PlayerAppearanceLike],
) -> EngineResult[PlayerRoleReport]:
    """Bir oyuncunun primary + secondary rolünü tespit et."""
    stats = _aggregate_per_90(player_external_id, list(appearances))
    primary, confidence, secondary = _classify_role(stats)
    report = PlayerRoleReport(
        player_external_id=player_external_id,
        primary_role=primary,
        confidence=round(confidence, 2),
        secondary_role=secondary,
        inputs={k: v for k, v in stats.items() if isinstance(v, (int, float))},
    )
    audit = AuditRecord(
        engine=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        subject_type="player",
        subject_id=player_external_id,
        metric="player_role",
        value={
            "primary_role": primary,
            "confidence": report.confidence,
            "secondary_role": secondary,
        },
        inputs={
            **report.inputs,
            "position_code": stats.get("position_code", ""),
        },
        formula=(
            "rule-based: position + per-90 thresholds; "
            "CB: D-pos+shots<1 → ball_playing if passes>=55 acc>=88 else traditional; "
            "F: target_man if fouls_drawn>=3 & dribbles<1.5; "
            "M: defensive_mid if shots<0.5 & fouls_comm>=1.5; "
            "deep_playmaker if passes>=50 acc>=85 shots<1.5; else box_to_box"
        ),
    )
    return EngineResult(value=report, audit=audit)
