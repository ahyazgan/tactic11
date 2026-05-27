"""Set-piece analiz motoru — duran top etkinliği + savunma zayıflığı.

Profesyonel kullanım: "Bu rakibe out-swinger köşe vuruşu öner — son 6 maçta
4 set-piece golü o bölgeden yedi." (A1 Set-piece, freelancer brief).

Veri girdisi: `Shot` listesi (app/domain/shot.py). Shot.pattern alanları:
- "corner_kick" / "free_kick" / "set_piece" → set-piece türleri
- "open_play" → set-piece DEĞİL (atla)

Bu engine veri ingest'i değil; saf agregasyon yapar. Caller StatsBomb adapter
ya da kendi event-feed'inden Shot listesi hazırlar.

Sınırlama: Set-piece "konsept tipleri" (in-swinger, out-swinger, kısa pas)
Shot.pattern enum'unda yok — bunlar event payload'unda ek alan (technique,
sub_pattern) gerektirir. Şu an binary (set-piece mi değil mi) ayrım yeterli;
sub-pattern enrichment v2'de gelir.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass
from typing import Literal

from app.audit import AuditRecord, EngineResult
from app.domain import Shot

ENGINE_NAME = "engine.set_piece"
ENGINE_VERSION = "1"

# Set-piece pattern set'i
SET_PIECE_PATTERNS = frozenset(("corner_kick", "free_kick", "set_piece"))

SetPieceType = Literal["corner_kick", "free_kick", "set_piece", "all"]


@dataclass(frozen=True)
class SetPieceReport:
    """Bir takım için set-piece etkinliği veya zayıflığı."""
    subject_team_id: int
    set_piece_type: str  # "corner_kick" | "free_kick" | "set_piece" | "all"
    role: str  # "offensive" (attı) | "defensive" (yedi)
    shot_count: int
    goal_count: int
    conversion_rate: float  # goals / shots
    total_xg: float | None  # eğer Shot'larda xG yoksa None
    xg_per_shot: float | None


def compute_set_piece_efficiency(
    team_external_id: int,
    shots: Iterable[Shot],
    *,
    role: str = "offensive",
    set_piece_type: SetPieceType = "all",
    use_xg: bool = False,
) -> EngineResult[SetPieceReport]:
    """Bir takımın set-piece etkinliği veya savunma zayıflığı.

    `role`:
      - "offensive": team atttığı set-piece şutlar
      - "defensive": team yediği set-piece şutlar (rakip atış)
    `set_piece_type`:
      - "all": tüm set-piece türleri toplamı
      - "corner_kick" / "free_kick" / "set_piece": tek türe filtre
    `use_xg`: True ise xG hesabı ile birlikte (caller xG enriched Shot'lar
    göndermeli — bu engine xG hesaplamaz, sadece read'er; xG compute
    `engine.xg` üzerinde).
    """
    if role not in ("offensive", "defensive"):
        raise ValueError(f"role: 'offensive'|'defensive' (geldi: {role!r})")

    # Filter — set-piece only + set_piece_type
    relevant = []
    for s in shots:
        if s.pattern not in SET_PIECE_PATTERNS:
            continue
        if set_piece_type != "all" and s.pattern != set_piece_type:
            continue
        relevant.append(s)

    n_shots = len(relevant)
    n_goals = sum(1 for s in relevant if s.is_goal)
    conversion = n_goals / n_shots if n_shots else 0.0

    total_xg: float | None = None
    xg_per_shot: float | None = None
    if use_xg and relevant:
        # Shot domain modelinde xg yok — engine.xg.compute_shot_xg ile dış'tan
        # zenginleştirilmesi gerekir. Burada placeholder: caller xg_total
        # parametresini ileride aktarabilir; şimdilik kendimiz hesaplıyoruz.
        from app.engine.xg import compute_shot_xg
        xg_values = [compute_shot_xg(s, mode="geometric").value.xg for s in relevant]
        total_xg = round(sum(xg_values), 4)
        xg_per_shot = round(total_xg / n_shots, 4) if n_shots else None

    report = SetPieceReport(
        subject_team_id=team_external_id,
        set_piece_type=set_piece_type,
        role=role,
        shot_count=n_shots,
        goal_count=n_goals,
        conversion_rate=round(conversion, 4),
        total_xg=total_xg,
        xg_per_shot=xg_per_shot,
    )
    audit = AuditRecord(
        engine=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        subject_type="team",
        subject_id=team_external_id,
        metric="set_piece_efficiency",
        value=asdict(report),
        inputs={
            "role": role,
            "set_piece_type": set_piece_type,
            "use_xg": use_xg,
            "total_shots_examined": sum(1 for _ in shots) if False else None,  # iterable consumed
        },
        formula=(
            "filter pattern in {corner_kick, free_kick, set_piece} + "
            "set_piece_type filter; conversion_rate = goals / shots; "
            "total_xg via engine.xg.compute_shot_xg(mode=geometric) if use_xg=True"
        ),
    )
    return EngineResult(value=report, audit=audit)
