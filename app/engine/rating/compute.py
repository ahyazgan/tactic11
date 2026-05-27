"""Takım rating'i — basit, formüle dayanan, açıklanabilir.

Form raporundan tek skorlu bir gösterge üretir:
    rating = ppg * PPG_WEIGHT + goal_diff_per_match * GD_WEIGHT

**v2:** Aynı formülün ev-only ve dep-only subsetlere de uygulanır;
`home_rating` ve `away_rating` çıktılara eklenir. Takımların evde ve
deplasmanda farklı profil sergilemesi yaygın (ev avantajı, atmosfer,
seyahat yorgunluğu) — rotasyon ve fikstür-zorluğu kararları için
side-aware sinyal lazım.

`overall_rating` mevcut "rating" alanı; geriye uyumlu.

Hedef "doğru" rating değil, açıklanabilir bir baseline. ML-tabanlı rating
Ufuk 3'te `engine.predict`'in yanına eklenecek (xGBoost rakip-spesifik).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass

from app.audit import AuditRecord, EngineResult
from app.engine._protocols import MatchLike
from app.engine.form import FormReport, compute_form

ENGINE_NAME = "engine.rating"
ENGINE_VERSION = "2"  # v1 → v2: home_rating + away_rating eklendi

PPG_WEIGHT = 50.0  # 0–150 aralığı (ppg 0–3)
GD_WEIGHT = 10.0


@dataclass(frozen=True)
class TeamRating:
    rating: float  # overall (mevcut)
    points_per_game: float
    goal_diff_per_match: float
    matches_considered: int

    # v2 — side-aware ratings; takımın ev/dep profili
    home_rating: float  # sadece ev maçlarından (matches_played=0 ise 0.0)
    away_rating: float  # sadece dep maçlarından (matches_played=0 ise 0.0)
    home_matches: int
    away_matches: int


def _score_from(form: FormReport) -> float:
    """ppg × PPG_WEIGHT + gd_per_match × GD_WEIGHT; boş form → 0."""
    if form.matches_played == 0:
        return 0.0
    gdpm = form.goal_diff / form.matches_played
    return round(form.points_per_game * PPG_WEIGHT + gdpm * GD_WEIGHT, 3)


def compute_team_rating(
    team_external_id: int,
    matches: Iterable[MatchLike],
    *,
    last_n: int = 10,
    time_decay_rate: float = 0.0,
) -> EngineResult[TeamRating]:
    """Takım rating'i — overall + side-aware (ev/dep).

    `last_n`: overall ve her side subset için ayrı uygulanır (yani son N ev
    maç + son N dep maç olabilir; sample asimetrisi raporda görünür).
    `time_decay_rate`: compute_form'a doğrudan geçer; rate>0 ise gf/ga
    per-match averages zaman-ağırlıklı (PR #22 form v4).
    """
    # Tek seferde materialize — engine.form iki kez tüketecek, generator olamaz
    materialized = list(matches)

    form_all = compute_form(
        team_external_id, materialized, last_n=last_n, time_decay_rate=time_decay_rate
    ).value

    # Side subsetleri — sadece team'in o tarafta oynadığı maçları geçir
    home_only = [m for m in materialized if m.home_team_external_id == team_external_id]
    away_only = [m for m in materialized if m.away_team_external_id == team_external_id]
    form_home = compute_form(
        team_external_id, home_only, last_n=last_n, time_decay_rate=time_decay_rate
    ).value
    form_away = compute_form(
        team_external_id, away_only, last_n=last_n, time_decay_rate=time_decay_rate
    ).value

    overall = _score_from(form_all)
    home_r = _score_from(form_home)
    away_r = _score_from(form_away)

    if form_all.matches_played == 0:
        gdpm_overall = 0.0
        ppg_overall = 0.0
    else:
        gdpm_overall = round(form_all.goal_diff / form_all.matches_played, 3)
        ppg_overall = form_all.points_per_game

    rating = TeamRating(
        rating=overall,
        points_per_game=ppg_overall,
        goal_diff_per_match=gdpm_overall,
        matches_considered=form_all.matches_played,
        home_rating=home_r,
        away_rating=away_r,
        home_matches=form_home.matches_played,
        away_matches=form_away.matches_played,
    )

    audit = AuditRecord(
        engine=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        subject_type="team",
        subject_id=team_external_id,
        metric="team_rating",
        value=asdict(rating),
        inputs={
            "last_n": last_n,
            "time_decay_rate": time_decay_rate,
            "ppg": ppg_overall,
            "goal_diff": form_all.goal_diff,
            "matches_played": form_all.matches_played,
            "home_matches": form_home.matches_played,
            "away_matches": form_away.matches_played,
        },
        formula=(
            f"rating = ppg*{PPG_WEIGHT} + (goal_diff/matches)*{GD_WEIGHT}; "
            "home_rating ve away_rating aynı formülün ev-only ve dep-only "
            "subsetlerine uygulanmasıyla; boş subset → 0.0"
        ),
    )
    return EngineResult(value=rating, audit=audit)
