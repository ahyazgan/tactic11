"""Matchup Grid — rakip zayıflık × bizim güç eşleştirme matrisi (Faz 5 #21).

Maç öncesi en kritik soru: "Rakibin zayıf olduğu yerde biz güçlü müyüz?"

Bu engine üç kanalda (sol/orta/sağ) iki tarafı çakıştırır:
- Bizim atak gücü (final-third girişleri o kanaldan)
- Rakibin savunma zayıflığı (o kanalda az defansif aksiyon)
- Eşleşme skoru = our_strength × opp_weakness

En yüksek skorlu kanal = "saldır buradan". En düşük = "rakip burada güçlü".

Saf hesap. Bizim event + rakip event'i ayrı alır, kanal bazında çakıştırır.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.audit import AuditRecord, EngineResult
from app.domain import Carry, DefensiveAction, PassEvent

ENGINE_NAME = "engine.matchup_grid"
ENGINE_VERSION = "1"

FINAL_THIRD_X = 66.7
LEFT_Y_MAX = 33.3
RIGHT_Y_MIN = 66.7

CHANNELS = ("left", "central", "right")


def _channel(y: float) -> str:
    if y < LEFT_Y_MAX:
        return "left"
    if y > RIGHT_Y_MIN:
        return "right"
    return "central"


@dataclass(frozen=True)
class ChannelMatchup:
    channel: str
    our_attacks: int            # bizim final-third girişlerimiz (o kanaldan)
    opp_def_actions: int        # rakibin o kanaldaki savunma aksiyonu
    our_strength: float          # our_attacks normalize (0-1)
    opp_weakness: float          # 1 - opp_def normalize (0-1)
    matchup_score: float         # our_strength × opp_weakness
    verdict: str                 # "exploit" | "neutral" | "avoid"


@dataclass(frozen=True)
class MatchupGridReport:
    my_team_external_id: int
    opponent_team_external_id: int
    matches_analyzed: int
    by_channel: tuple[ChannelMatchup, ...]
    best_channel: str            # en yüksek matchup_score
    worst_channel: str           # en düşük (rakip güçlü)
    recommendation: str          # human-readable Türkçe


def _verdict(score: float, max_score: float) -> str:
    if max_score <= 0:
        return "neutral"
    ratio = score / max_score
    if ratio >= 0.75:
        return "exploit"
    if ratio <= 0.35:
        return "avoid"
    return "neutral"


def compute_matchup_grid(
    *,
    my_team_external_id: int,
    opponent_team_external_id: int,
    our_passes: Iterable[PassEvent],
    our_carries: Iterable[Carry],
    opponent_def_actions: Iterable[DefensiveAction],
    matches_analyzed: int = 1,
) -> EngineResult[MatchupGridReport]:
    """Üç kanalda bizim atak gücü × rakip savunma zayıflığı eşleştirme.

    `our_passes`/`our_carries` bizim takımın final-third giriş eventleri,
    `opponent_def_actions` rakibin tüm defansif aksiyonları (kanal başına
    yoğunluk için).
    """
    # Bizim atak: final third'a giriş kanal başına
    our_attacks = {c: 0 for c in CHANNELS}
    for p in our_passes:
        if p.team_external_id != my_team_external_id:
            continue
        if p.start_x >= FINAL_THIRD_X or p.end_x < FINAL_THIRD_X:
            continue
        our_attacks[_channel(p.end_y)] += 1
    for c in our_carries:
        if c.team_external_id != my_team_external_id:
            continue
        if c.start_x >= FINAL_THIRD_X or c.end_x < FINAL_THIRD_X:
            continue
        our_attacks[_channel(c.end_y)] += 1

    # Rakip savunma: kanal başına defansif aksiyon
    opp_defs = {c: 0 for c in CHANNELS}
    for d in opponent_def_actions:
        if d.team_external_id != opponent_team_external_id:
            continue
        opp_defs[_channel(d.y)] += 1

    total_attacks = sum(our_attacks.values()) or 1
    max_opp_def = max(opp_defs.values()) or 1

    channels: list[ChannelMatchup] = []
    for ch in CHANNELS:
        our_strength = our_attacks[ch] / total_attacks
        # opp_weakness: o kanalda defansif aksiyon ne kadar az → zayıf
        opp_weakness = 1.0 - (opp_defs[ch] / max_opp_def)
        score = round(our_strength * opp_weakness, 4)
        channels.append(ChannelMatchup(
            channel=ch,
            our_attacks=our_attacks[ch],
            opp_def_actions=opp_defs[ch],
            our_strength=round(our_strength, 3),
            opp_weakness=round(opp_weakness, 3),
            matchup_score=score,
            verdict="neutral",  # geçici; aşağıda max'a göre
        ))
    max_score = max((c.matchup_score for c in channels), default=0.0)
    # Verdict'leri max'a göre yeniden hesapla
    channels = [
        ChannelMatchup(
            channel=c.channel, our_attacks=c.our_attacks,
            opp_def_actions=c.opp_def_actions, our_strength=c.our_strength,
            opp_weakness=c.opp_weakness, matchup_score=c.matchup_score,
            verdict=_verdict(c.matchup_score, max_score),
        )
        for c in channels
    ]
    best = max(channels, key=lambda c: c.matchup_score)
    worst = min(channels, key=lambda c: c.matchup_score)

    side_tr = {"left": "sol kanat", "central": "merkez", "right": "sağ kanat"}
    if total_attacks <= 1:
        rec = "Yeterli atak verisi yok"
    else:
        rec = (
            f"En iyi eşleşme {side_tr[best.channel]} "
            f"(skor {best.matchup_score:.2f}); rakip {side_tr[worst.channel]}'ta "
            f"güçlü — oradan kaçının"
        )

    report = MatchupGridReport(
        my_team_external_id=my_team_external_id,
        opponent_team_external_id=opponent_team_external_id,
        matches_analyzed=matches_analyzed,
        by_channel=tuple(channels),
        best_channel=best.channel,
        worst_channel=worst.channel,
        recommendation=rec,
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="match", subject_id=my_team_external_id,
        metric="matchup_grid",
        value={
            "best_channel": best.channel,
            "worst_channel": worst.channel,
            "by_channel": [
                {"channel": c.channel, "our_strength": c.our_strength,
                 "opp_weakness": c.opp_weakness, "score": c.matchup_score,
                 "verdict": c.verdict}
                for c in channels
            ],
        },
        inputs={
            "opponent_team_external_id": opponent_team_external_id,
            "final_third_x": FINAL_THIRD_X,
            "matches_analyzed": matches_analyzed,
        },
        formula="matchup_score = our_strength(attack share) × opp_weakness(1 - def share)",
    )
    return EngineResult(value=report, audit=audit)
