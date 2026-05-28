"""Off-ball Runs — top sahibi olmayan hareketler (carry-tabanlı proxy).

Gerçek off-ball run analizi tracking gerektirir (StatsBomb 360); biz event
proxy kullanıyoruz:

Bir oyuncunun TAKIM POSSESSION'i süresince yaptığı carry sayısı / takımın
toplam possession sayısı = "her possession başına oyuncunun aktif
katılımı". Pas alıp götüren (carry) = run karşılığı yapan oyuncu.

Yüksek değer = sürekli boşluk arayan oyuncu (Mahrez, Salah inverted winger).

Saf hesap. Carry + PossessionSequence içerikleriyle çalışır.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.audit import AuditRecord, EngineResult
from app.domain import Carry, PassEvent

ENGINE_NAME = "engine.off_ball_runs"
ENGINE_VERSION = "1"

# Hareket sayma eşiği: 8 birim üzeri carry (= yaklaşık 8m saha ilerlemesi)
MIN_CARRY_LENGTH = 8.0
# İleri-doğru (run) sayılmak için end_x > start_x
FORWARD_BIAS = True


@dataclass(frozen=True)
class OffBallRunsReport:
    player_external_id: int
    team_external_id: int
    matches_analyzed: int
    team_possessions: int           # toplam possession sequence sayısı
    player_carries: int              # oyuncunun anlamlı (>MIN_CARRY_LENGTH) carry'leri
    forward_runs: int                # ileri doğru carry'ler
    runs_per_possession: float       # player_carries / team_possessions
    forward_runs_per_90: float       # 90 dakikaya normalize
    player_minutes_played: float     # caller'ın verdiği


def compute_off_ball_runs(
    *,
    player_external_id: int,
    team_external_id: int,
    all_carries: Iterable[Carry],
    all_passes: Iterable[PassEvent],
    player_minutes_played: float,
    matches_analyzed: int = 1,
) -> EngineResult[OffBallRunsReport]:
    """Oyuncunun anlamlı top-taşıma sayısı + per-possession yoğunluğu.

    `all_passes` possession sayısını çıkarmak için kullanılır (PassEvent.possession_id).
    `player_minutes_played` caller (lineup/appearance) tarafından sağlanır.
    """
    # Takımın toplam unique possession sayısı (passes üzerinden)
    team_possession_ids = {
        p.possession_id for p in all_passes
        if p.team_external_id == team_external_id and p.possession_id is not None
    }

    player_carries = [
        c for c in all_carries
        if c.player_external_id == player_external_id
    ]
    significant = [
        c for c in player_carries
        if ((c.end_x - c.start_x) ** 2 + (c.end_y - c.start_y) ** 2) ** 0.5
        >= MIN_CARRY_LENGTH
    ]
    forward = [c for c in significant if c.end_x > c.start_x] if FORWARD_BIAS else significant

    rpp = len(significant) / len(team_possession_ids) if team_possession_ids else 0.0
    per_90 = (len(forward) / player_minutes_played) * 90 if player_minutes_played > 0 else 0.0

    report = OffBallRunsReport(
        player_external_id=player_external_id,
        team_external_id=team_external_id,
        matches_analyzed=matches_analyzed,
        team_possessions=len(team_possession_ids),
        player_carries=len(significant),
        forward_runs=len(forward),
        runs_per_possession=round(rpp, 3),
        forward_runs_per_90=round(per_90, 2),
        player_minutes_played=player_minutes_played,
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="player", subject_id=player_external_id,
        metric="off_ball_runs",
        value={
            "player_carries": report.player_carries,
            "forward_runs": report.forward_runs,
            "runs_per_possession": report.runs_per_possession,
            "forward_runs_per_90": report.forward_runs_per_90,
        },
        inputs={
            "min_carry_length": MIN_CARRY_LENGTH,
            "forward_bias": FORWARD_BIAS,
            "team_possessions": len(team_possession_ids),
            "matches_analyzed": matches_analyzed,
        },
        formula="player carries >= min_length; per possession or per 90",
    )
    return EngineResult(value=report, audit=audit)
