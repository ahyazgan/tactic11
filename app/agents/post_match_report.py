"""PostMatchReportAgent — maç bittiğinde tahmin vs gerçek özeti.

Kalibrasyon loop'unu (predict → reconcile → narrate) müşteri tarafına
yansıtır: "tahminimiz Y dedi, gerçek X oldu, ne öğrendik?"

Context: {"match_external_id": int}
Output: {
  match_external_id, home_team, away_team, kickoff,
  actual: {home_score, away_score, outcome},
  prediction: {expected_home_goals, expected_away_goals, prob_*, most_likely_score},
  delta: {goal_diff_home, goal_diff_away, outcome_match (bool)},
  ai_brief: str  ("tahmin haklı çıktı" / "fark şuradan geldi")
}

Persist edilmiş tahmin yoksa (predictions tablosunda satır yoksa):
ValueError → "tahmin saklanmamış".
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.base import Agent, AgentResult
from app.ai import AnthropicClient, ClaudeCommentator
from app.db import models
from app.sports import football


def _outcome_from_scores(home: int, away: int) -> str:
    if home > away:
        return "home"
    if away > home:
        return "away"
    return "draw"


class PostMatchReportAgent(Agent):
    """Maç sonu: actual vs predicted karşılaştırması + AI yorumu."""

    name = "post_match_report"
    version = "1"

    def __init__(self, *, commentator: ClaudeCommentator | None = None):
        self._commentator = commentator or ClaudeCommentator(AnthropicClient())

    def run(self, session: Session, *, context: dict[str, Any]) -> AgentResult:
        match_id = context.get("match_external_id")
        if match_id is None:
            raise ValueError("context.match_external_id zorunlu")

        match = session.execute(
            select(models.Match).where(
                models.Match.sport == football.SPORT_NAME,
                models.Match.external_id == int(match_id),
            )
        ).scalar_one_or_none()
        if match is None:
            raise ValueError(f"match {match_id} bulunamadı")
        if match.status not in football.FINISHED_STATUSES:
            raise ValueError(
                f"match {match_id} henüz bitmedi (status={match.status})"
            )
        if match.home_score is None or match.away_score is None:
            raise ValueError(f"match {match_id}: skor henüz yok")

        # En son predict (engine.predict) — params_hash farklı satırlar olabilir,
        # en güncel updated_at'i al
        pred_row = session.execute(
            select(models.Prediction)
            .where(
                models.Prediction.sport == football.SPORT_NAME,
                models.Prediction.match_external_id == int(match_id),
                models.Prediction.engine == "engine.predict",
            )
            .order_by(models.Prediction.updated_at.desc())
        ).scalars().first()
        if pred_row is None:
            raise ValueError(
                f"match {match_id}: kaydedilmiş tahmin yok "
                "(önce /matches/{id}/predict çağrılmalı)"
            )
        pred_payload = json.loads(pred_row.predicted_value_json)

        actual_outcome = _outcome_from_scores(match.home_score, match.away_score)
        # Tahminin most-likely outcome'ı: max prob_{home_win,draw,away_win}
        probs = {
            "home": float(pred_payload.get("prob_home_win", 0.0)),
            "draw": float(pred_payload.get("prob_draw", 0.0)),
            "away": float(pred_payload.get("prob_away_win", 0.0)),
        }
        predicted_outcome = max(probs.items(), key=lambda kv: kv[1])[0]
        outcome_match = predicted_outcome == actual_outcome

        expected_home = float(pred_payload.get("expected_home_goals", 0.0))
        expected_away = float(pred_payload.get("expected_away_goals", 0.0))

        # AI brief — generic explain ile değil, custom doğrudan prompt
        ai_brief = _build_brief(
            commentator=self._commentator,
            home_id=match.home_team_external_id,
            away_id=match.away_team_external_id,
            actual_h=match.home_score, actual_a=match.away_score,
            actual_outcome=actual_outcome,
            expected_h=expected_home, expected_a=expected_away,
            probs=probs, predicted_outcome=predicted_outcome,
        )

        output = {
            "match_external_id": int(match_id),
            "home_team_external_id": match.home_team_external_id,
            "away_team_external_id": match.away_team_external_id,
            "kickoff": match.kickoff.isoformat(),
            "actual": {
                "home_score": match.home_score,
                "away_score": match.away_score,
                "outcome": actual_outcome,
            },
            "prediction": {
                "expected_home_goals": expected_home,
                "expected_away_goals": expected_away,
                "prob_home_win": probs["home"],
                "prob_draw": probs["draw"],
                "prob_away_win": probs["away"],
                "predicted_outcome": predicted_outcome,
                "engine_version": pred_row.engine_version,
            },
            "delta": {
                "goal_diff_home": match.home_score - expected_home,
                "goal_diff_away": match.away_score - expected_away,
                "outcome_match": outcome_match,
            },
            "ai_brief": ai_brief,
        }
        summary = (
            f"{match.home_team_external_id} {match.home_score}-{match.away_score} "
            f"{match.away_team_external_id}: "
            f"tahmin {predicted_outcome} → gerçek {actual_outcome} "
            f"({'doğru' if outcome_match else 'yanlış'})"
        )
        return AgentResult(
            output_json=output, summary=summary,
            subject_type="match", subject_id=int(match_id),
        )


def _build_brief(
    *,
    commentator: ClaudeCommentator,
    home_id: int, away_id: int,
    actual_h: int, actual_a: int, actual_outcome: str,
    expected_h: float, expected_a: float,
    probs: dict[str, float], predicted_outcome: str,
) -> str:
    """ClaudeCommentator's free-form text via low-level method or stub."""
    if commentator._client.is_stub():
        return (
            f"[stub:post_match] {home_id} {actual_h}-{actual_a} {away_id}: "
            f"tahmin {predicted_outcome} ({int(probs[predicted_outcome] * 100)}%) "
            f"→ gerçek {actual_outcome}. ANTHROPIC_API_KEY yok."
        )
    system = (
        "Sen futbol teknik ekibine kalibrasyon raporu sunan bir analiz asistanısın. "
        "Tahminle gerçek arasındaki farkı 100-150 kelime ile değerlendir. "
        "Sayıları tekrar etme; 'neden farklı çıktı / haklı çıktı' yorumla."
    )
    user = (
        f"Maç: takım {home_id} (ev) vs takım {away_id} (dep)\n"
        f"Tahmin: beklenen goller {expected_h:.2f}-{expected_a:.2f}; "
        f"olasılıklar ev/X/dep = "
        f"{probs['home']:.2f}/{probs['draw']:.2f}/{probs['away']:.2f} "
        f"→ ön gördüğümüz sonuç: {predicted_outcome}\n"
        f"Gerçek: {actual_h}-{actual_a} → {actual_outcome}\n\n"
        "Brief'i şu sırada yaz: (1) tahmin haklı/yanlış mıydı, "
        "(2) gol farkı önemli mi, (3) bu tek maç model güncellemesini "
        "gerektirir mi yoksa varyans mı?"
    )
    return commentator._call(system, user, max_tokens=300)
