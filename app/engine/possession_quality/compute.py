"""Possession Quality — possession başına pas + ilerleme metresi.

Tanım: bir takımın her possession_id sequence'i için:
- pas sayısı
- toplam ileri-x ilerlemesi (end_x - start_x toplamı)
- şutla sonlanıp sonlanmadığı

Yüksek pass-per-poss + yüksek ilerleme = kaliteli possession (City, Bayern).
Düşük pass + bir-iki uzun pas → direct play.

Saf hesap. PassEvent listesi possession_id ile gruplanır.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.audit import AuditRecord, EngineResult
from app.domain import PassEvent, Shot

ENGINE_NAME = "engine.possession_quality"
ENGINE_VERSION = "1"


@dataclass(frozen=True)
class PossessionQualityReport:
    team_external_id: int
    matches_analyzed: int
    sequences_analyzed: int
    avg_passes_per_sequence: float
    avg_x_progression: float          # ortalama ileri ilerleme (saha birimleri)
    shot_ending_share: float          # şutla sonlanan possession yüzdesi
    quality_score: float              # composite: passes/seq × prog × shot_share
    label: str                        # "elite" | "good" | "weak"


def _label(score: float) -> str:
    if score >= 5.0:
        return "elite"
    if score >= 2.0:
        return "good"
    return "weak"


def compute_possession_quality(
    team_external_id: int,
    all_passes: Iterable[PassEvent],
    all_shots: Iterable[Shot],
    *,
    matches_analyzed: int = 1,
) -> EngineResult[PossessionQualityReport]:
    sequences: dict[int, list[PassEvent]] = {}
    for p in all_passes:
        if p.team_external_id != team_external_id or p.possession_id is None:
            continue
        sequences.setdefault(p.possession_id, []).append(p)

    # Şutla sonlanan possession'lar: shot.minute aralığında pas grubunun
    # zaman aralığına denk geliyorsa True. Yaklaşım: aynı dakikada veya hemen
    # sonraki dakikada şut varsa "şutla sonlandı".
    shot_minutes = sorted(s.minute for s in all_shots)

    pass_counts: list[int] = []
    progressions: list[float] = []
    shot_endings = 0
    for _pid, passes in sequences.items():
        pass_counts.append(len(passes))
        prog = sum(p.end_x - p.start_x for p in passes)
        progressions.append(prog)
        last_minute = max(p.minute for p in passes)
        # Şut last_minute - last_minute + 0.20 (12 sn) içinde mi
        for sm in shot_minutes:
            if last_minute <= sm <= last_minute + 0.20:
                shot_endings += 1
                break

    n = len(sequences)
    if n == 0:
        report = PossessionQualityReport(
            team_external_id=team_external_id,
            matches_analyzed=matches_analyzed,
            sequences_analyzed=0,
            avg_passes_per_sequence=0.0,
            avg_x_progression=0.0,
            shot_ending_share=0.0,
            quality_score=0.0,
            label="insufficient_data",
        )
    else:
        avg_passes = sum(pass_counts) / n
        avg_prog = sum(progressions) / n
        shot_share = shot_endings / n
        # Kompozit: ilerlemeyi 30 birime böl, normalize; sonra üç çarp
        norm_prog = max(0.0, avg_prog) / 30.0
        score = avg_passes * norm_prog * (1 + shot_share)
        report = PossessionQualityReport(
            team_external_id=team_external_id,
            matches_analyzed=matches_analyzed,
            sequences_analyzed=n,
            avg_passes_per_sequence=round(avg_passes, 2),
            avg_x_progression=round(avg_prog, 2),
            shot_ending_share=round(shot_share, 3),
            quality_score=round(score, 2),
            label=_label(score),
        )

    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="team", subject_id=team_external_id,
        metric="possession_quality",
        value={
            "sequences_analyzed": report.sequences_analyzed,
            "avg_passes_per_sequence": report.avg_passes_per_sequence,
            "avg_x_progression": report.avg_x_progression,
            "shot_ending_share": report.shot_ending_share,
            "quality_score": report.quality_score,
            "label": report.label,
        },
        inputs={"matches_analyzed": matches_analyzed},
        formula="group passes by possession_id; score = passes × (prog/30) × (1 + shot_share)",
    )
    return EngineResult(value=report, audit=audit)
