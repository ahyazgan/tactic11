"""Asistan tool katalogu — Claude tool_use için.

Her tool: (1) JSON schema (Claude'a verilir), (2) handler fonksiyonu
(Session ile çalışır, JSON-serileştirilebilir dict döner).

Tüm tool'lar READ-ONLY: DB sorgular, engine'ler çağrır; yazma yok.
"Manager assistant" güvenli bir co-pilot — yan etki yok.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.data.cache.store import cache_get
from app.db import models
from app.engine.form import compute_form
from app.engine.load import compute_player_load
from app.engine.opponent import compute_head_to_head
from app.engine.predict import compute_predict
from app.engine.predict_ml import CACHE_KEY as ML_CACHE_KEY
from app.engine.predict_ml import CACHE_SOURCE as ML_CACHE_SOURCE
from app.engine.rating import compute_team_rating
from app.engine.schedule import compute_schedule
from app.sports import football

MAX_TOOL_ITERATIONS = 8  # Claude loop'u sonsuz dönmesin


def _team_matches(session: Session, team_id: int) -> list[models.Match]:
    return list(
        session.execute(
            select(models.Match).where(
                models.Match.sport == football.SPORT_NAME,
                or_(
                    models.Match.home_team_external_id == team_id,
                    models.Match.away_team_external_id == team_id,
                ),
            ).order_by(models.Match.kickoff.desc())
        ).scalars()
    )


# --------------------------------------------------------------------------- #
# Tool handlers — her biri JSON-serializable dict döner
# --------------------------------------------------------------------------- #


def tool_get_team_form(session: Session, *, team_external_id: int, last_n: int = 5) -> dict:
    matches = _team_matches(session, int(team_external_id))
    if not matches:
        return {"error": f"team {team_external_id}: hiç maç yok"}
    f = compute_form(int(team_external_id), matches, last_n=int(last_n)).value
    return {
        "team_id": int(team_external_id),
        "matches_played": f.matches_played,
        "wins": f.wins, "draws": f.draws, "losses": f.losses,
        "goals_for": f.goals_for, "goals_against": f.goals_against,
        "points_per_game": f.points_per_game,
        "last_results": list(f.last_results),
    }


def tool_get_team_rating(session: Session, *, team_external_id: int) -> dict:
    matches = _team_matches(session, int(team_external_id))
    if not matches:
        return {"error": f"team {team_external_id}: hiç maç yok"}
    r = compute_team_rating(int(team_external_id), matches, last_n=10).value
    return {
        "team_id": int(team_external_id),
        "rating": r.rating,
        "home_rating": r.home_rating,
        "away_rating": r.away_rating,
        "points_per_game": r.points_per_game,
        "matches_considered": r.matches_considered,
    }


def tool_get_head_to_head(session: Session, *, team_a: int, team_b: int) -> dict:
    h2h_matches = list(
        session.execute(
            select(models.Match).where(
                models.Match.sport == football.SPORT_NAME,
                or_(
                    (models.Match.home_team_external_id == int(team_a))
                    & (models.Match.away_team_external_id == int(team_b)),
                    (models.Match.home_team_external_id == int(team_b))
                    & (models.Match.away_team_external_id == int(team_a)),
                ),
            )
        ).scalars()
    )
    h = compute_head_to_head(int(team_a), int(team_b), h2h_matches).value
    return {
        "team_a": int(team_a), "team_b": int(team_b),
        "matches_played": h.matches_played,
        "team_a_wins": h.team_a_wins, "draws": h.draws, "team_b_wins": h.team_b_wins,
        "team_a_goals": h.team_a_goals, "team_b_goals": h.team_b_goals,
    }


def tool_get_match_info(session: Session, *, match_external_id: int) -> dict:
    m = session.execute(
        select(models.Match).where(
            models.Match.sport == football.SPORT_NAME,
            models.Match.external_id == int(match_external_id),
        )
    ).scalar_one_or_none()
    if m is None:
        return {"error": f"match {match_external_id}: yok"}
    return {
        "match_id": m.external_id,
        "kickoff": m.kickoff.isoformat(),
        "status": m.status,
        "home_team_id": m.home_team_external_id,
        "away_team_id": m.away_team_external_id,
        "home_score": m.home_score,
        "away_score": m.away_score,
        "league_id": m.league_external_id,
        "season": m.season,
    }


def tool_get_match_prediction(
    session: Session, *, match_external_id: int, use_ml: bool = True,
) -> dict:
    m = session.execute(
        select(models.Match).where(
            models.Match.sport == football.SPORT_NAME,
            models.Match.external_id == int(match_external_id),
        )
    ).scalar_one_or_none()
    if m is None:
        return {"error": f"match {match_external_id}: yok"}

    home_prior = list(
        session.execute(
            select(models.Match).where(
                models.Match.sport == football.SPORT_NAME,
                models.Match.kickoff < m.kickoff,
                or_(
                    models.Match.home_team_external_id == m.home_team_external_id,
                    models.Match.away_team_external_id == m.home_team_external_id,
                ),
            )
        ).scalars()
    )
    away_prior = list(
        session.execute(
            select(models.Match).where(
                models.Match.sport == football.SPORT_NAME,
                models.Match.kickoff < m.kickoff,
                or_(
                    models.Match.home_team_external_id == m.away_team_external_id,
                    models.Match.away_team_external_id == m.away_team_external_id,
                ),
            )
        ).scalars()
    )
    home_form = compute_form(m.home_team_external_id, home_prior, last_n=5).value
    away_form = compute_form(m.away_team_external_id, away_prior, last_n=5).value

    rho = -0.12
    ml_status = "default"
    if use_ml:
        ml_cache = cache_get(session, source=ML_CACHE_SOURCE, key=ML_CACHE_KEY)
        if ml_cache and ml_cache.get("best_rho") is not None:
            rho = float(ml_cache["best_rho"])
            ml_status = "fresh"
        else:
            ml_status = "untrained"

    p = compute_predict(
        home_form, away_form,
        home_team_id=m.home_team_external_id,
        away_team_id=m.away_team_external_id,
        rho=rho,
    ).value
    return {
        "match_id": int(match_external_id),
        "home_team_id": m.home_team_external_id,
        "away_team_id": m.away_team_external_id,
        "expected_home_goals": p.expected_home_goals,
        "expected_away_goals": p.expected_away_goals,
        "prob_home_win": p.prob_home_win,
        "prob_draw": p.prob_draw,
        "prob_away_win": p.prob_away_win,
        "most_likely_score": list(p.most_likely_score),
        "rho_used": rho,
        "ml_status": ml_status,
        "low_confidence": p.low_confidence,
    }


def tool_get_upcoming_matches(
    session: Session, *, team_external_id: int, days: int = 14,
) -> dict:
    sample = session.execute(
        select(models.Match).where(
            models.Match.sport == football.SPORT_NAME,
            or_(
                models.Match.home_team_external_id == int(team_external_id),
                models.Match.away_team_external_id == int(team_external_id),
            ),
        ).limit(1)
    ).scalar_one_or_none()
    if sample is None:
        return {"team_id": int(team_external_id), "upcoming": []}
    ref_tz = sample.kickoff.tzinfo
    now = datetime.now(ref_tz)
    horizon = now + timedelta(days=int(days))
    rows = list(
        session.execute(
            select(models.Match).where(
                models.Match.sport == football.SPORT_NAME,
                or_(
                    models.Match.home_team_external_id == int(team_external_id),
                    models.Match.away_team_external_id == int(team_external_id),
                ),
                models.Match.kickoff > now,
                models.Match.kickoff <= horizon,
                ~models.Match.status.in_(football.FINISHED_STATUSES),
            ).order_by(models.Match.kickoff)
        ).scalars()
    )
    return {
        "team_id": int(team_external_id),
        "upcoming": [
            {
                "match_id": r.external_id,
                "kickoff": r.kickoff.isoformat(),
                "home_team_id": r.home_team_external_id,
                "away_team_id": r.away_team_external_id,
                "is_home": r.home_team_external_id == int(team_external_id),
            }
            for r in rows
        ],
    }


def tool_get_player_load(
    session: Session, *, player_external_ids: list[int], window_days: int = 14,
) -> dict:
    sample = session.execute(
        select(models.PlayerAppearance).where(
            models.PlayerAppearance.sport == football.SPORT_NAME,
            models.PlayerAppearance.player_external_id.in_(player_external_ids),
        ).limit(1)
    ).scalar_one_or_none()
    if sample is None:
        return {"loads": []}
    ref_tz = sample.kickoff.tzinfo
    now = datetime.now(ref_tz)
    cutoff = now - timedelta(days=int(window_days))
    rows = list(
        session.execute(
            select(models.PlayerAppearance).where(
                models.PlayerAppearance.sport == football.SPORT_NAME,
                models.PlayerAppearance.player_external_id.in_(player_external_ids),
                models.PlayerAppearance.kickoff >= cutoff,
            )
        ).scalars()
    )
    by_player: dict[int, list] = {pid: [] for pid in player_external_ids}
    for r in rows:
        by_player.setdefault(r.player_external_id, []).append(r)
    loads = []
    for pid in player_external_ids:
        v = compute_player_load(
            pid, by_player.get(pid, []),
            window_days=int(window_days), now=now,
        ).value
        loads.append({
            "player_id": pid,
            "minutes_in_window": v.minutes_in_window,
            "minutes_per_week": v.minutes_per_week,
            "matches_in_window": v.matches_in_window,
            "high_load": v.high_load,
        })
    return {"window_days": int(window_days), "loads": loads}


def tool_get_team_schedule(
    session: Session, *, team_external_id: int, horizon_days: int = 30,
) -> dict:
    matches = _team_matches(session, int(team_external_id))
    if not matches:
        return {"error": f"team {team_external_id}: hiç maç yok"}
    ref_tz = matches[0].kickoff.tzinfo
    now = datetime.now(ref_tz)
    s = compute_schedule(
        int(team_external_id), matches, now=now, horizon_days=int(horizon_days),
    ).value
    return {
        "team_id": int(team_external_id),
        "upcoming_count": s.upcoming_count,
        "matches_next_7d": s.matches_next_7d,
        "matches_next_14d": s.matches_next_14d,
        "dense_schedule": s.dense_schedule,
        "days_until_next_match": s.days_until_next_match,
        "next_kickoffs": list(s.next_kickoffs),
    }


def tool_get_ml_status(session: Session) -> dict:
    cached = cache_get(session, source=ML_CACHE_SOURCE, key=ML_CACHE_KEY)
    if cached and cached.get("best_rho") is not None:
        return {
            "status": "fresh",
            "best_rho": cached.get("best_rho"),
            "sample_count": cached.get("sample_count"),
            "best_log_loss": cached.get("best_log_loss"),
        }
    return {"status": "untrained", "best_rho": None}


def tool_list_team_recent_players(
    session: Session, *, team_external_id: int, last_n_matches: int = 10,
) -> dict:
    """Takımın son N maçında oynayan oyuncu listesi (roster proxy).

    PlayerAppearance team_id taşımaz; bu yüzden takımın son N maçındaki
    appearance'ları al, unique player_id'leri dön.
    """
    matches = _team_matches(session, int(team_external_id))[: int(last_n_matches)]
    if not matches:
        return {"team_id": int(team_external_id), "players": []}
    match_ids = [m.external_id for m in matches]
    rows = list(
        session.execute(
            select(models.PlayerAppearance).where(
                models.PlayerAppearance.sport == football.SPORT_NAME,
                models.PlayerAppearance.match_external_id.in_(match_ids),
            )
        ).scalars()
    )
    by_player: dict[int, int] = {}
    for r in rows:
        by_player[r.player_external_id] = by_player.get(r.player_external_id, 0) + r.minutes
    players = [
        {"player_id": pid, "total_minutes_in_recent_matches": mins}
        for pid, mins in sorted(by_player.items(), key=lambda kv: kv[1], reverse=True)
    ]
    return {
        "team_id": int(team_external_id),
        "scanned_matches": len(match_ids),
        "players": players,
    }


# --------------------------------------------------------------------------- #
# Tool registry — name → (schema, handler)
# --------------------------------------------------------------------------- #


_TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "get_team_form",
        "description": "Bir takımın son N maçındaki form raporu (W-D-L, gol, ppg).",
        "input_schema": {
            "type": "object",
            "properties": {
                "team_external_id": {"type": "integer"},
                "last_n": {"type": "integer", "default": 5},
            },
            "required": ["team_external_id"],
        },
    },
    {
        "name": "get_team_rating",
        "description": "Takım kompozit rating'i + ev/dep ayrımı (son 10 maç).",
        "input_schema": {
            "type": "object",
            "properties": {"team_external_id": {"type": "integer"}},
            "required": ["team_external_id"],
        },
    },
    {
        "name": "get_head_to_head",
        "description": "İki takımın tarihsel karşılaşma kaydı.",
        "input_schema": {
            "type": "object",
            "properties": {
                "team_a": {"type": "integer"},
                "team_b": {"type": "integer"},
            },
            "required": ["team_a", "team_b"],
        },
    },
    {
        "name": "get_match_info",
        "description": "Bir maçın temel bilgisi (kickoff, status, takımlar, skor).",
        "input_schema": {
            "type": "object",
            "properties": {"match_external_id": {"type": "integer"}},
            "required": ["match_external_id"],
        },
    },
    {
        "name": "get_match_prediction",
        "description": (
            "Maç için olasılık tahmini (Poisson+DC); use_ml=true ise "
            "öğrenilmiş ρ'yu cache'ten okur."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "match_external_id": {"type": "integer"},
                "use_ml": {"type": "boolean", "default": True},
            },
            "required": ["match_external_id"],
        },
    },
    {
        "name": "get_upcoming_matches",
        "description": "Takımın önümüzdeki N gündeki maçları (sıralı).",
        "input_schema": {
            "type": "object",
            "properties": {
                "team_external_id": {"type": "integer"},
                "days": {"type": "integer", "default": 14},
            },
            "required": ["team_external_id"],
        },
    },
    {
        "name": "get_player_load",
        "description": "Oyuncu listesi için yük raporu (dakika/hafta, high_load flag).",
        "input_schema": {
            "type": "object",
            "properties": {
                "player_external_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                },
                "window_days": {"type": "integer", "default": 14},
            },
            "required": ["player_external_ids"],
        },
    },
    {
        "name": "get_team_schedule",
        "description": "Takım fikstür yoğunluğu raporu (önümüzdeki N gün).",
        "input_schema": {
            "type": "object",
            "properties": {
                "team_external_id": {"type": "integer"},
                "horizon_days": {"type": "integer", "default": 30},
            },
            "required": ["team_external_id"],
        },
    },
    {
        "name": "get_ml_status",
        "description": "ML kalibrasyon model durumu (fresh/untrained, best ρ).",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "list_team_recent_players",
        "description": (
            "Takımın son N maçında oynayan oyuncu listesi (roster proxy). "
            "player_id ve toplam dakika döner."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "team_external_id": {"type": "integer"},
                "last_n_matches": {"type": "integer", "default": 10},
            },
            "required": ["team_external_id"],
        },
    },
]


_TOOL_HANDLERS: dict[str, Callable[..., dict[str, Any]]] = {
    "get_team_form": tool_get_team_form,
    "get_team_rating": tool_get_team_rating,
    "get_head_to_head": tool_get_head_to_head,
    "get_match_info": tool_get_match_info,
    "get_match_prediction": tool_get_match_prediction,
    "get_upcoming_matches": tool_get_upcoming_matches,
    "get_player_load": tool_get_player_load,
    "get_team_schedule": tool_get_team_schedule,
    "get_ml_status": tool_get_ml_status,
    "list_team_recent_players": tool_list_team_recent_players,
}


def get_tool_schemas() -> list[dict[str, Any]]:
    """Claude messages.create için tools listesi (deep copy).

    Faz 5: v2 + v3 tool schemaları otomatik dahil olur (Sprint 1 + Sprint 2-5).
    """
    from app.assistant.tools_v2 import V2_TOOL_SCHEMAS
    from app.assistant.tools_v3 import V3_TOOL_SCHEMAS
    return (
        [dict(s) for s in _TOOL_SCHEMAS]
        + [dict(s) for s in V2_TOOL_SCHEMAS]
        + [dict(s) for s in V3_TOOL_SCHEMAS]
    )


def execute_tool(session: Session, name: str, input_args: dict[str, Any]) -> str:
    """Tool çağırır, JSON string olarak sonucu döner. Bilinmeyen tool → error JSON.

    Faz 5: v1 → v2 → v3 fallback sırası (Sprint 1 → Sprint 2-5).
    """
    from app.assistant.tools_v2 import V2_TOOL_HANDLERS
    from app.assistant.tools_v3 import V3_TOOL_HANDLERS
    handler = (
        _TOOL_HANDLERS.get(name)
        or V2_TOOL_HANDLERS.get(name)
        or V3_TOOL_HANDLERS.get(name)
    )
    if handler is None:
        return json.dumps({"error": f"bilinmeyen tool: {name}"})
    try:
        result = handler(session, **input_args)
    except Exception as e:  # noqa: BLE001 — Claude hatayı string olarak görsün
        result = {"error": f"tool {name} hata: {type(e).__name__}: {e}"}
    return json.dumps(result, ensure_ascii=False)
