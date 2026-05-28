"""Manager Assistant — Faz 5 chat tools (Sprint 1).

Mevcut tools.py'ya ek olarak 13 yeni tool. Hepsi mevcut agent/engine'leri
sarmalıyor; yeni motor yazılmadı.

Tools:
- get_lineup_recommendation, get_opponent_scout, get_substitution_advice,
  get_tactical_adjustment, get_training_plan, get_injury_load,
  get_set_piece_routine, get_player_feedback, get_pre_match_report,
  get_post_match_report, get_weekly_digest, get_team_tactical,
  compare_players
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

# --------------------------------------------------------------------------- #
# Agent-sarmalayan tool'lar
# --------------------------------------------------------------------------- #


def tool_get_lineup_recommendation(
    session: Session, *, team_external_id: int,
) -> dict[str, Any]:
    """Önerilen başlangıç 11'i."""
    from app.agents import LineupRecommendationAgent
    agent = LineupRecommendationAgent()
    try:
        result = agent.run(
            session, context={"team_external_id": team_external_id},
        )
    except (ValueError, RuntimeError) as e:
        return {"error": str(e)}
    return {
        "team_external_id": team_external_id,
        "summary": result.summary,
        "output": result.output_json,
    }


def tool_get_opponent_scout(
    session: Session, *, team_external_id: int,
) -> dict[str, Any]:
    """Sıradaki rakibin scout raporu."""
    from app.agents import NoUpcomingMatch, OpponentScoutAgent
    agent = OpponentScoutAgent()
    try:
        result = agent.run(
            session, context={"team_external_id": team_external_id},
        )
    except NoUpcomingMatch as e:
        return {"info": str(e)}
    except ValueError as e:
        return {"error": str(e)}
    return {
        "team_external_id": team_external_id,
        "summary": result.summary,
        "output": result.output_json,
    }


def tool_get_substitution_advice(
    session: Session, *, match_external_id: int, team_external_id: int,
) -> dict[str, Any]:
    """Maç içi sub önerisi (canlı veya retrospective)."""
    from app.agents import SubstitutionAdviceAgent
    agent = SubstitutionAdviceAgent()
    try:
        result = agent.run(session, context={
            "match_external_id": match_external_id,
            "team_external_id": team_external_id,
        })
    except (ValueError, RuntimeError) as e:
        return {"error": str(e)}
    return {"summary": result.summary, "output": result.output_json}


def tool_get_tactical_adjustment(
    session: Session, *, team_external_id: int,
    match_external_id: int | None = None,
) -> dict[str, Any]:
    """Taktiksel ayar önerisi (formation/press/line)."""
    from app.agents import TacticalAdjustmentAgent
    agent = TacticalAdjustmentAgent()
    ctx: dict[str, Any] = {"team_external_id": team_external_id}
    if match_external_id is not None:
        ctx["match_external_id"] = match_external_id
    try:
        result = agent.run(session, context=ctx)
    except (ValueError, RuntimeError) as e:
        return {"error": str(e)}
    return {"summary": result.summary, "output": result.output_json}


def tool_get_training_plan(
    session: Session, *, my_team_external_id: int,
    opponent_external_id: int,
) -> dict[str, Any]:
    """Haftalık antrenman planı (rakip profilinden drill önerileri)."""
    from app.agents import TrainingPlanAgent
    agent = TrainingPlanAgent()
    try:
        result = agent.run(session, context={
            "my_team_external_id": my_team_external_id,
            "opponent_external_id": opponent_external_id,
        })
    except (ValueError, RuntimeError) as e:
        return {"error": str(e)}
    return {"summary": result.summary, "output": result.output_json}


def tool_get_injury_load(
    session: Session, *, team_external_id: int,
) -> dict[str, Any]:
    """Yük + sakatlık riski raporu."""
    from app.agents import InjuryLoadAgent
    agent = InjuryLoadAgent()
    try:
        result = agent.run(
            session, context={"team_external_id": team_external_id},
        )
    except (ValueError, RuntimeError) as e:
        return {"error": str(e)}
    return {"summary": result.summary, "output": result.output_json}


def tool_get_set_piece_routine(
    session: Session, *, my_team_external_id: int,
    opponent_external_id: int, set_piece_type: str = "all",
) -> dict[str, Any]:
    """Rakibin zayıf zone × bizim güç → routine builder."""
    from app.data.loaders import load_team_events
    from app.engine.set_piece_routine import compute_set_piece_routine
    my_events = load_team_events(session, my_team_external_id, last_n=5)
    opp_events = load_team_events(session, opponent_external_id, last_n=5)
    if my_events.total == 0 or opp_events.total == 0:
        return {"info": "Yeterli event yok (iki takım için ingest gerekli)"}
    result = compute_set_piece_routine(
        my_team_external_id=my_team_external_id,
        opponent_team_external_id=opponent_external_id,
        my_offensive_shots=my_events.shots,
        opponent_defensive_shots=opp_events.shots,
        opponent_offensive_shots=opp_events.shots,
        set_piece_type=set_piece_type,
        matches_analyzed=min(len(my_events.match_ids), len(opp_events.match_ids)),
    )
    v = result.value
    return {
        "my_team_external_id": my_team_external_id,
        "opponent_external_id": opponent_external_id,
        "set_piece_type": set_piece_type,
        "avoid_zone": v.avoid_zone,
        "top_recommendations": [
            {
                "target_zone": r.target_zone, "technique": r.technique,
                "score": r.routine_score, "rationale": r.rationale,
            }
            for r in v.top_recommendations
        ],
    }


def tool_get_player_feedback(
    session: Session, *, match_external_id: int, player_external_id: int,
) -> dict[str, Any]:
    """Bireysel oyuncu maç-sonu rapor + top 3 alt-optimal pas."""
    from app.agents import PlayerFeedbackAgent
    agent = PlayerFeedbackAgent()
    try:
        result = agent.run(session, context={
            "match_external_id": match_external_id,
            "player_external_id": player_external_id,
        })
    except (ValueError, RuntimeError) as e:
        return {"error": str(e)}
    return {"summary": result.summary, "output": result.output_json}


def tool_get_pre_match_report(
    session: Session, *, team_external_id: int,
) -> dict[str, Any]:
    """Maç öncesi 200 kelime brief."""
    from app.agents import PreMatchReportAgent
    agent = PreMatchReportAgent()
    try:
        result = agent.run(
            session, context={"team_external_id": team_external_id},
        )
    except (ValueError, RuntimeError) as e:
        return {"error": str(e)}
    return {"summary": result.summary, "output": result.output_json}


def tool_get_post_match_report(
    session: Session, *, match_external_id: int,
) -> dict[str, Any]:
    """Maç sonrası özet rapor."""
    from app.agents import PostMatchReportAgent
    agent = PostMatchReportAgent()
    try:
        result = agent.run(
            session, context={"match_external_id": match_external_id},
        )
    except (ValueError, RuntimeError) as e:
        return {"error": str(e)}
    return {"summary": result.summary, "output": result.output_json}


def tool_get_weekly_digest(
    session: Session, *, league_external_id: int,
    season: int | None = None,
) -> dict[str, Any]:
    """Lig haftalık özet — son maçlar + öne çıkan trendler."""
    from app.agents import WeeklyDigestAgent
    agent = WeeklyDigestAgent()
    ctx: dict[str, Any] = {"league_external_id": league_external_id}
    if season is not None:
        ctx["season"] = season
    try:
        result = agent.run(session, context=ctx)
    except (ValueError, RuntimeError) as e:
        return {"error": str(e)}
    return {"summary": result.summary, "output": result.output_json}


def tool_get_team_tactical(
    session: Session, *, team_external_id: int, last_n: int = 10,
    opponent_id: int | None = None,
) -> dict[str, Any]:
    """Takım tactical-profile (PPDA, field_tilt, xT, vs.) batch çıktısı."""
    from app.data.loaders import load_team_events
    from app.engine.field_tilt import compute_field_tilt
    from app.engine.ppda import compute_ppda
    from app.engine.tempo import compute_tempo
    from app.engine.xt import compute_team_xt
    loaded = load_team_events(session, team_external_id, last_n=last_n)
    if loaded.total == 0:
        return {"info": "events tablosunda kayıt yok"}
    n = len(loaded.match_ids)
    out: dict[str, Any] = {
        "team_external_id": team_external_id,
        "matches_analyzed": n,
        "events_loaded": loaded.total,
    }
    try:
        ppda = compute_ppda(
            team_external_id, loaded.passes, loaded.defensive_actions,
            matches_analyzed=n,
        ).value
        out["ppda"] = ppda.ppda
        tempo = compute_tempo(
            team_external_id, loaded.passes, matches_analyzed=n,
        ).value
        out["tempo_label"] = tempo.label
        out["passes_per_minute"] = tempo.passes_per_minute
        xt = compute_team_xt(
            team_external_id, loaded.passes, loaded.carries,
        ).value
        out["team_xt_total"] = xt.total_xt
        if opponent_id:
            tilt = compute_field_tilt(
                team_external_id, opponent_id, loaded.passes,
            ).value
            out["field_tilt_team_share"] = tilt.team_a_tilt
    except (ValueError, ZeroDivisionError) as e:
        out["error"] = str(e)
    return out


def tool_compare_players(
    session: Session, *, target_player_external_id: int,
    candidate_player_external_ids: list[int],
    min_minutes: int = 180,
) -> dict[str, Any]:
    """player_similarity ile hedef oyuncuyu N adaya karşı benzerlik skorla."""
    from sqlalchemy import select

    from app.db import models
    from app.engine.player_similarity import compute_similar_players
    from app.sports import football
    # Tüm appearance'ları çek + by player grupla
    all_apps = list(session.execute(
        select(models.PlayerAppearance).where(
            models.PlayerAppearance.sport == football.SPORT_NAME,
        )
    ).scalars())
    by_pid: dict[int, list] = {}
    for a in all_apps:
        by_pid.setdefault(a.player_external_id, []).append(a)
    target_apps = by_pid.get(target_player_external_id, [])
    if not target_apps:
        return {"error": f"player {target_player_external_id} için appearance yok"}
    candidates = {
        pid: by_pid[pid] for pid in candidate_player_external_ids
        if pid != target_player_external_id and pid in by_pid
    }
    if not candidates:
        return {"info": "aday listesi boş (hiç appearance yok)"}
    result = compute_similar_players(
        target_player_external_id, target_apps, candidates,
        top_n=len(candidates), min_minutes=min_minutes,
    )
    return {
        "target_player_external_id": target_player_external_id,
        "matches": [
            {
                "player_id": m.player_external_id,
                "similarity": m.similarity,
                "minutes": m.total_minutes,
            }
            for m in result.value.top_matches
        ],
    }


# --------------------------------------------------------------------------- #
# Tool schemas — Claude messages.create format
# --------------------------------------------------------------------------- #

V2_TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "get_lineup_recommendation",
        "description": "Bir takımın sıradaki maçı için önerilen başlangıç 11'i.",
        "input_schema": {
            "type": "object",
            "properties": {
                "team_external_id": {"type": "integer"},
            },
            "required": ["team_external_id"],
        },
    },
    {
        "name": "get_opponent_scout",
        "description": "Sıradaki rakibin scout raporu (form + rating + H2H + taktiksel parmak izi).",
        "input_schema": {
            "type": "object",
            "properties": {
                "team_external_id": {"type": "integer"},
            },
            "required": ["team_external_id"],
        },
    },
    {
        "name": "get_substitution_advice",
        "description": "Belirli maçta sub önerisi (canlı veya retrospective).",
        "input_schema": {
            "type": "object",
            "properties": {
                "match_external_id": {"type": "integer"},
                "team_external_id": {"type": "integer"},
            },
            "required": ["match_external_id", "team_external_id"],
        },
    },
    {
        "name": "get_tactical_adjustment",
        "description": "Taktiksel ayar önerisi: formasyon/press/savunma hattı.",
        "input_schema": {
            "type": "object",
            "properties": {
                "team_external_id": {"type": "integer"},
                "match_external_id": {"type": "integer"},
            },
            "required": ["team_external_id"],
        },
    },
    {
        "name": "get_training_plan",
        "description": "Rakip profilinden 5 drill önerisi + haftalık antrenman briefi.",
        "input_schema": {
            "type": "object",
            "properties": {
                "my_team_external_id": {"type": "integer"},
                "opponent_external_id": {"type": "integer"},
            },
            "required": ["my_team_external_id", "opponent_external_id"],
        },
    },
    {
        "name": "get_injury_load",
        "description": "Takımdaki yüksek-yük oyuncular + sakatlık riski özeti.",
        "input_schema": {
            "type": "object",
            "properties": {
                "team_external_id": {"type": "integer"},
            },
            "required": ["team_external_id"],
        },
    },
    {
        "name": "get_set_piece_routine",
        "description": "Rakibin zayıf zone × bizim güç → 3 routine önerisi + avoid zone.",
        "input_schema": {
            "type": "object",
            "properties": {
                "my_team_external_id": {"type": "integer"},
                "opponent_external_id": {"type": "integer"},
                "set_piece_type": {
                    "type": "string",
                    "enum": ["all", "corner_kick", "free_kick", "set_piece"],
                },
            },
            "required": ["my_team_external_id", "opponent_external_id"],
        },
    },
    {
        "name": "get_player_feedback",
        "description": "Bireysel oyuncu maç-sonu rapor + top 3 alt-optimal pas örneği.",
        "input_schema": {
            "type": "object",
            "properties": {
                "match_external_id": {"type": "integer"},
                "player_external_id": {"type": "integer"},
            },
            "required": ["match_external_id", "player_external_id"],
        },
    },
    {
        "name": "get_pre_match_report",
        "description": "Sıradaki maç öncesi 200 kelime brief.",
        "input_schema": {
            "type": "object",
            "properties": {
                "team_external_id": {"type": "integer"},
            },
            "required": ["team_external_id"],
        },
    },
    {
        "name": "get_post_match_report",
        "description": "Bir maçın sonrası özet rapor (tahmin vs sonuç + xG + oyuncu öne çıkanlar).",
        "input_schema": {
            "type": "object",
            "properties": {
                "match_external_id": {"type": "integer"},
            },
            "required": ["match_external_id"],
        },
    },
    {
        "name": "get_weekly_digest",
        "description": "Lig haftalık özet — son maçlar + öne çıkan trendler.",
        "input_schema": {
            "type": "object",
            "properties": {
                "league_external_id": {"type": "integer"},
                "season": {"type": "integer"},
            },
            "required": ["league_external_id"],
        },
    },
    {
        "name": "get_team_tactical",
        "description": "Takım tactical batch: PPDA + tempo + team_xt (+ rakip verilirse field_tilt).",
        "input_schema": {
            "type": "object",
            "properties": {
                "team_external_id": {"type": "integer"},
                "last_n": {"type": "integer"},
                "opponent_id": {"type": "integer"},
            },
            "required": ["team_external_id"],
        },
    },
    {
        "name": "compare_players",
        "description": "Hedef oyuncuyu N aday oyuncuya karşı benzerlik skoruyla sırala.",
        "input_schema": {
            "type": "object",
            "properties": {
                "target_player_external_id": {"type": "integer"},
                "candidate_player_external_ids": {
                    "type": "array", "items": {"type": "integer"},
                },
                "min_minutes": {"type": "integer"},
            },
            "required": [
                "target_player_external_id",
                "candidate_player_external_ids",
            ],
        },
    },
]


V2_TOOL_HANDLERS: dict[str, Callable[..., dict[str, Any]]] = {
    "get_lineup_recommendation": tool_get_lineup_recommendation,
    "get_opponent_scout": tool_get_opponent_scout,
    "get_substitution_advice": tool_get_substitution_advice,
    "get_tactical_adjustment": tool_get_tactical_adjustment,
    "get_training_plan": tool_get_training_plan,
    "get_injury_load": tool_get_injury_load,
    "get_set_piece_routine": tool_get_set_piece_routine,
    "get_player_feedback": tool_get_player_feedback,
    "get_pre_match_report": tool_get_pre_match_report,
    "get_post_match_report": tool_get_post_match_report,
    "get_weekly_digest": tool_get_weekly_digest,
    "get_team_tactical": tool_get_team_tactical,
    "compare_players": tool_compare_players,
}
