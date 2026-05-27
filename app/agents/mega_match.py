"""MegaMatchAgent — bir maç için kapsamlı çok-bölümlü brief ("teknik direktör paketi").

PreMatchReportAgent kısa (200 kelime) ve form+h2h üstünde durur.
MegaMatch bütün engine'leri (form, rating, opponent, predict, fixture_difficulty,
schedule, tracking — varsa) tek bir 600-800 kelimelik 6-bölümlü rapora sentezler.

Context: {"match_external_id": int}
Output bölümleri:
  1. tactical_preview       — form + rating dengesi
  2. key_matchups           — h2h trendler
  3. recent_form_analysis   — momentum & GD per match
  4. prediction_confidence  — predict (Poisson+DC) + ML status
  5. scheduling_context     — fikstür yoğunluğu + zorluk
  6. tracking_insight       — varsa ball-zone distribution (yoksa skip)
  7. watch_out_factors      — uyarı bayrakları (low sample, eksik veri)
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.agents.base import Agent, AgentResult
from app.ai import AnthropicClient, ClaudeCommentator
from app.api.serialize import engine_result_to_dict
from app.data.cache.store import cache_get
from app.data.sources.fixture_tracking import FixtureTrackingSource
from app.db import models
from app.engine.fixture_difficulty import OpponentRating, compute_fixture_difficulty
from app.engine.form import compute_form
from app.engine.opponent import compute_head_to_head
from app.engine.predict import compute_predict
from app.engine.predict_ml import CACHE_KEY as ML_CACHE_KEY
from app.engine.predict_ml import CACHE_SOURCE as ML_CACHE_SOURCE
from app.engine.rating import compute_team_rating
from app.engine.schedule import compute_schedule
from app.engine.tracking import compute_ball_zone_distribution
from app.sports import football


class MegaMatchAgent(Agent):
    """Kapsamlı maç analizi — birden çok engine sentezi + tracking opsiyonel."""

    name = "mega_match"
    version = "1"

    def __init__(self, *, commentator: ClaudeCommentator | None = None, last_n: int = 5):
        self._commentator = commentator or ClaudeCommentator(AnthropicClient())
        self._last_n = last_n

    def run(self, session: Session, *, context: dict[str, Any]) -> AgentResult:
        match_id = context.get("match_external_id")
        if match_id is None:
            raise ValueError("context.match_external_id zorunlu")
        match_id = int(match_id)

        match = session.execute(
            select(models.Match).where(
                models.Match.sport == football.SPORT_NAME,
                models.Match.external_id == match_id,
            )
        ).scalar_one_or_none()
        if match is None:
            raise ValueError(f"match {match_id} bulunamadı")

        home_id = match.home_team_external_id
        away_id = match.away_team_external_id

        # Leakage guard
        def _prior(tid: int):
            return list(
                session.execute(
                    select(models.Match).where(
                        models.Match.sport == football.SPORT_NAME,
                        models.Match.kickoff < match.kickoff,
                        or_(
                            models.Match.home_team_external_id == tid,
                            models.Match.away_team_external_id == tid,
                        ),
                    )
                ).scalars()
            )

        home_prior = _prior(home_id)
        away_prior = _prior(away_id)

        home_form = compute_form(home_id, home_prior, last_n=self._last_n)
        away_form = compute_form(away_id, away_prior, last_n=self._last_n)
        home_rating = compute_team_rating(home_id, home_prior, last_n=10)
        away_rating = compute_team_rating(away_id, away_prior, last_n=10)

        h2h_matches = [
            m for m in home_prior
            if (m.home_team_external_id == home_id and m.away_team_external_id == away_id)
            or (m.home_team_external_id == away_id and m.away_team_external_id == home_id)
        ]
        h2h = compute_head_to_head(home_id, away_id, h2h_matches)

        # Predict — ML cache varsa learned ρ
        ml_cache = cache_get(session, source=ML_CACHE_SOURCE, key=ML_CACHE_KEY)
        if ml_cache and ml_cache.get("best_rho") is not None:
            rho = float(ml_cache["best_rho"])
            ml_status = "fresh"
        else:
            rho = -0.12  # engine.predict default
            ml_status = "untrained"

        predict = compute_predict(
            home_form.value, away_form.value,
            home_team_id=home_id, away_team_id=away_id,
            rho=rho,
        )

        # Schedule + fixture difficulty (home tarafı)
        ref_tz = match.kickoff.tzinfo
        now = datetime.now(ref_tz) if ref_tz else datetime.utcnow()
        schedule = compute_schedule(home_id, home_prior + [match], now=now, horizon_days=30)

        ratings_for_difficulty: dict[int, OpponentRating] = {}
        for tid, rr_res in ((home_id, home_rating), (away_id, away_rating)):
            rr = rr_res.value
            if rr.matches_considered:
                ratings_for_difficulty[tid] = OpponentRating(
                    home_rating=rr.home_rating if rr.home_matches else None,
                    away_rating=rr.away_rating if rr.away_matches else None,
                    overall_rating=rr.rating,
                )
        horizon = now + timedelta(days=30)
        home_scoped = [m for m in home_prior + [match] if m.kickoff <= horizon]
        difficulty = compute_fixture_difficulty(
            home_id, home_scoped, ratings_for_difficulty, now=now,
        )

        # Tracking — varsa
        tracking_src = FixtureTrackingSource()
        tracking_result = None
        if tracking_src.has_fixture(match_id):
            frames = list(tracking_src.get_match_frames(match_id))
            tracking_result = compute_ball_zone_distribution(frames)

        # Watch-out factors
        watch_outs: list[str] = []
        if home_form.value.matches_played < 3:
            watch_outs.append("Ev formunda az örneklem (<3 maç)")
        if away_form.value.matches_played < 3:
            watch_outs.append("Dep formunda az örneklem (<3 maç)")
        if predict.value.low_confidence:
            watch_outs.append(f"Tahmin düşük güven (sample={predict.value.sample_size})")
        if h2h.value.matches_played == 0:
            watch_outs.append("Geçmiş H2H yok — h2h dominance ihmal edilebilir")
        if ml_status == "untrained":
            watch_outs.append("ML kalibrasyon henüz train edilmedi (default ρ)")

        ai_brief = _build_mega_brief(
            commentator=self._commentator,
            home_id=home_id, away_id=away_id,
            home_form=home_form, away_form=away_form,
            home_rating=home_rating, away_rating=away_rating,
            h2h=h2h, predict=predict, schedule=schedule, difficulty=difficulty,
            tracking_result=tracking_result, ml_status=ml_status,
            watch_outs=watch_outs,
            kickoff_iso=match.kickoff.isoformat(),
        )

        output = {
            "match_external_id": match_id,
            "home_team_external_id": home_id,
            "away_team_external_id": away_id,
            "kickoff": match.kickoff.isoformat(),
            "sections": {
                "tactical_preview": {
                    "home_rating": engine_result_to_dict(home_rating),
                    "away_rating": engine_result_to_dict(away_rating),
                },
                "key_matchups": engine_result_to_dict(h2h),
                "recent_form_analysis": {
                    "home_form": engine_result_to_dict(home_form),
                    "away_form": engine_result_to_dict(away_form),
                },
                "prediction_confidence": {
                    "predict": engine_result_to_dict(predict),
                    "ml_status": ml_status,
                    "rho_used": rho,
                },
                "scheduling_context": {
                    "home_schedule": engine_result_to_dict(schedule),
                    "home_fixture_difficulty": engine_result_to_dict(difficulty),
                },
                "tracking_insight": (
                    engine_result_to_dict(tracking_result) if tracking_result else None
                ),
                "watch_out_factors": watch_outs,
            },
            "ai_brief": ai_brief,
        }
        pv = predict.value
        summary = (
            f"Mega brief — {home_id} vs {away_id}: "
            f"tahmin {int(pv.prob_home_win * 100)}/{int(pv.prob_draw * 100)}/"
            f"{int(pv.prob_away_win * 100)}, ML {ml_status}, "
            f"watch-out={len(watch_outs)}"
        )
        return AgentResult(
            output_json=output, summary=summary,
            subject_type="match", subject_id=match_id,
        )


def _build_mega_brief(
    *, commentator: ClaudeCommentator, home_id: int, away_id: int,
    home_form, away_form, home_rating, away_rating, h2h, predict,
    schedule, difficulty, tracking_result, ml_status: str,
    watch_outs: list[str], kickoff_iso: str,
) -> str:
    if commentator._client.is_stub():
        pv = predict.value
        return (
            f"[stub:mega_match] {home_id} vs {away_id} @ {kickoff_iso[:10]}: "
            f"tahmin {int(pv.prob_home_win*100)}/{int(pv.prob_draw*100)}/"
            f"{int(pv.prob_away_win*100)}, ML {ml_status}, "
            f"{len(watch_outs)} uyarı. ANTHROPIC_API_KEY yok."
        )
    hf, af = home_form.value, away_form.value
    hr, ar = home_rating.value, away_rating.value
    pv = predict.value
    sv, dv = schedule.value, difficulty.value
    system = (
        "Sen futbol teknik direktörüne maç öncesi KAPSAMLI brief sunan "
        "analiz asistanısın. 400-500 kelime, 6 paragraf. Sırayla:\n"
        "1) Taktiksel önizleme (form+rating dengesi)\n"
        "2) Kilit karşılaşmalar (H2H)\n"
        "3) Son form analizi (momentum)\n"
        "4) Tahmin güveni (olasılıklar + model durumu)\n"
        "5) Fikstür bağlamı (yoğunluk + zorluk)\n"
        "6) Dikkat edilmesi gerekenler\n"
        "Sayıları tekrar etme; ÇIKARIM yaz. Her paragraf 2-3 cümle."
    )
    tracking_line = ""
    if tracking_result is not None:
        tv = tracking_result.value
        tracking_line = (
            f"\nTracking (ball-zone): "
            f"def %{int(tv.defensive_third_fraction*100)} / "
            f"orta %{int(tv.middle_third_fraction*100)} / "
            f"hücum %{int(tv.attacking_third_fraction*100)}"
        )
    user = (
        f"Maç: {home_id} (ev) vs {away_id} (dep) @ {kickoff_iso}\n\n"
        f"EV: form {hf.wins}-{hf.draws}-{hf.losses} (ppg {hf.points_per_game}), "
        f"rating {hr.rating} (home_rating {hr.home_rating})\n"
        f"DEP: form {af.wins}-{af.draws}-{af.losses} (ppg {af.points_per_game}), "
        f"rating {ar.rating} (away_rating {ar.away_rating})\n"
        f"H2H ({h2h.value.matches_played} maç): ev={h2h.value.team_a_wins} "
        f"X={h2h.value.draws} dep={h2h.value.team_b_wins}\n"
        f"Tahmin: λ_ev={pv.expected_home_goals} λ_dep={pv.expected_away_goals}; "
        f"olasılık ev/X/dep = {pv.prob_home_win:.2f}/{pv.prob_draw:.2f}/{pv.prob_away_win:.2f}; "
        f"en olası skor {pv.most_likely_score}; ML durumu {ml_status}\n"
        f"Ev programı: 30g'de {sv.upcoming_count} maç, dense={sv.dense_schedule}; "
        f"fikstür zorluğu={dv.weighted_difficulty}\n"
        + tracking_line +
        f"\nUyarılar: {', '.join(watch_outs) if watch_outs else 'yok'}"
    )
    return commentator._call(system, user, max_tokens=900)
