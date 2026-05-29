"""Manager Assistant — Faz 5 Sprint 2-5 chat tools (v3 katmanı).

V2'ye ek 6 yeni tool. Mevcut Sprint 2-5 engine'lerini sarmalar; yeni motor
yazılmadı. DB'deki `PlayerAppearance` üzerinden takım kadrosunu / yük
listesini otomatik üretir, böylece çoğu tool sadece `team_external_id`
parametresiyle anlamlı sonuç döner.

Tools:
- get_proactive_alerts     — engine.proactive_alerts
- get_matchup_grid          — engine.matchup_grid
- get_available_squad       — engine.available_squad
- get_injury_risk           — engine.injury_risk (bir oyuncu)
- get_squad_depth           — engine.squad_depth
- get_rotation_plan         — engine.rotation_plan
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

# --------------------------------------------------------------------------- #
# Yardımcılar — takım kadrosu + yük loader (PlayerAppearance üzerinden)
# --------------------------------------------------------------------------- #


def _team_player_ids(session: Session, team_external_id: int) -> list[int]:
    """Takımın PlayerAppearance'larından benzersiz oyuncu listesi."""
    from app.db import models
    from app.sports import football
    rows = session.execute(
        select(models.PlayerAppearance.player_external_id)
        .where(
            models.PlayerAppearance.sport == football.SPORT_NAME,
            models.PlayerAppearance.team_external_id == team_external_id,
        )
        .distinct()
    ).scalars().all()
    return [int(r) for r in rows]


def _player_appearances(
    session: Session, player_external_id: int,
) -> list[Any]:
    """Bir oyuncunun tüm appearance kayıtları (kickoff sıralı)."""
    from app.db import models
    from app.sports import football
    return list(session.execute(
        select(models.PlayerAppearance)
        .where(
            models.PlayerAppearance.sport == football.SPORT_NAME,
            models.PlayerAppearance.player_external_id == player_external_id,
        )
        .order_by(models.PlayerAppearance.kickoff)
    ).scalars())


def _build_team_player_loads(
    session: Session, team_external_id: int, *, window_days: int = 14,
) -> list[dict[str, Any]]:
    """Takımın her oyuncusu için PlayerLoad → rotation/proactive dict listesi.

    Çıktı: rotation_plan + proactive_alerts'in beklediği dict şema:
        [{player_external_id, risk_level, minutes_per_week, back_to_back_count}, ...]
    """
    from app.engine.load import compute_player_load
    pids = _team_player_ids(session, team_external_id)
    loads: list[dict[str, Any]] = []
    for pid in pids:
        apps = _player_appearances(session, pid)
        if not apps:
            continue
        try:
            r = compute_player_load(pid, apps, window_days=window_days).value
        except (ValueError, ZeroDivisionError):
            continue
        loads.append({
            "player_external_id": pid,
            "risk_level": r.risk_level,
            "minutes_per_week": r.minutes_per_week,
            "back_to_back_count": r.back_to_back_count,
        })
    return loads


# --------------------------------------------------------------------------- #
# 1) Proactive alerts — takım yük + kontrat uyarıları kompoziti
# --------------------------------------------------------------------------- #


def tool_get_proactive_alerts(
    session: Session, *,
    team_external_id: int,
    upcoming_count: int = 0,
    dense_schedule: bool = False,
    horizon_days: int = 14,
    contract_warnings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Yük/zaaf/sözleşme proaktif uyarılar — kritik/uyarı sayımı + liste."""
    from app.engine.proactive_alerts import compute_proactive_alerts
    loads = _build_team_player_loads(
        session, team_external_id, window_days=horizon_days,
    )
    if not loads and not contract_warnings:
        return {"info": "appearance + contract verisi yok"}
    result = compute_proactive_alerts(
        team_external_id,
        player_loads=loads,
        upcoming_count=upcoming_count,
        dense_schedule=dense_schedule,
        horizon_days=horizon_days,
        contract_warnings=contract_warnings or [],
    )
    v = result.value
    return {
        "team_external_id": team_external_id,
        "total_alerts": v.total_alerts,
        "critical_count": v.critical_count,
        "warning_count": v.warning_count,
        "alerts": [
            {
                "level": getattr(a, "level", None),
                "kind": getattr(a, "kind", None),
                "subject_id": getattr(a, "subject_id", None),
                "message": getattr(a, "message", None),
            }
            for a in v.alerts
        ],
    }


# --------------------------------------------------------------------------- #
# 2) Matchup grid — kanal bazlı bizim güç × rakip zayıflık
# --------------------------------------------------------------------------- #


def tool_get_matchup_grid(
    session: Session, *,
    my_team_external_id: int,
    opponent_team_external_id: int,
    last_n: int = 5,
) -> dict[str, Any]:
    """Üç kanalda eşleşme matrisi — best/worst kanal + tavsiye."""
    from app.data.loaders import load_team_events
    from app.engine.matchup_grid import compute_matchup_grid
    my = load_team_events(session, my_team_external_id, last_n=last_n)
    opp = load_team_events(session, opponent_team_external_id, last_n=last_n)
    if my.total == 0 or opp.total == 0:
        return {"info": "Yeterli event yok (iki takım için ingest gerekli)"}
    result = compute_matchup_grid(
        my_team_external_id=my_team_external_id,
        opponent_team_external_id=opponent_team_external_id,
        our_passes=my.passes,
        our_carries=my.carries,
        opponent_def_actions=opp.defensive_actions,
        matches_analyzed=min(len(my.match_ids), len(opp.match_ids)),
    )
    v = result.value
    return {
        "my_team_external_id": my_team_external_id,
        "opponent_team_external_id": opponent_team_external_id,
        "matches_analyzed": v.matches_analyzed,
        "best_channel": v.best_channel,
        "worst_channel": v.worst_channel,
        "recommendation": v.recommendation,
        "by_channel": [
            {
                "channel": c.channel,
                "our_attacks": c.our_attacks,
                "opp_def_actions": c.opp_def_actions,
                "matchup_score": c.matchup_score,
                "verdict": c.verdict,
            }
            for c in v.by_channel
        ],
    }


# --------------------------------------------------------------------------- #
# 3) Available squad — müsait kadro ön-filtre
# --------------------------------------------------------------------------- #


def tool_get_available_squad(
    session: Session, *,
    team_external_id: int,
    squad: list[dict[str, Any]] | None = None,
    window_days: int = 14,
) -> dict[str, Any]:
    """Müsait kadro — sakat/cezalı + yüksek-yük doubtful.

    `squad` parametresi opsiyonel: verilirse direkt kullanılır
    (`[{player_id, position?, injured?, suspended?, risk_level?}]`).
    Verilmezse appearance'tan kadro üretilir; sakatlık/ceza bilgisi DB'de
    yok → sadece yük risk seviyesi ile doubtful/available ayrımı yapılır.
    """
    from app.engine.available_squad import compute_available_squad
    if squad is None:
        loads = _build_team_player_loads(
            session, team_external_id, window_days=window_days,
        )
        if not loads:
            return {"info": "appearance verisi yok ve squad parametresi verilmedi"}
        squad = [
            {
                "player_id": ld["player_external_id"],
                "position": None,
                "risk_level": ld["risk_level"],
            }
            for ld in loads
        ]
    result = compute_available_squad(team_external_id, squad)
    v = result.value
    return {
        "team_external_id": team_external_id,
        "total_squad": v.total_squad,
        "available_count": v.available_count,
        "doubtful_count": v.doubtful_count,
        "unavailable_count": v.unavailable_count,
        "players": [
            {
                "player_id": p.player_external_id,
                "status": p.status,
                "reason": p.reason,
                "position": p.position,
                "risk_level": p.risk_level,
            }
            for p in v.players
        ],
    }


# --------------------------------------------------------------------------- #
# 4) Injury risk — tek oyuncu için ACWR + yaş + sıklık kompoziti
# --------------------------------------------------------------------------- #


def tool_get_injury_risk(
    session: Session, *,
    player_external_id: int,
    age: int | None = None,
    window_days: int = 14,
) -> dict[str, Any]:
    """Sakatlık riski (0-100) — DB'den appearance + heuristic ACWR ile."""
    from app.engine.injury_risk import compute_injury_risk
    from app.engine.load import compute_player_load
    apps = _player_appearances(session, player_external_id)
    if not apps:
        return {"info": f"player {player_external_id} için appearance yok"}
    try:
        load_report = compute_player_load(
            player_external_id, apps, window_days=window_days,
        ).value
    except (ValueError, ZeroDivisionError) as e:
        return {"error": f"load hesaplanamadı: {e}"}

    # ACWR girdileri: son 7g (acute) + son 28g (chronic haftalık ort.)
    now = datetime.now(UTC)
    cut_7d = now - timedelta(days=7)
    cut_28d = now - timedelta(days=28)
    acute_7d = sum(
        int(a.minutes or 0) for a in apps if a.kickoff and a.kickoff >= cut_7d
    )
    chronic_28d = sum(
        int(a.minutes or 0) for a in apps if a.kickoff and a.kickoff >= cut_28d
    )
    chronic_avg = chronic_28d / 4.0 if chronic_28d > 0 else None

    result = compute_injury_risk(
        player_external_id,
        minutes_per_week=load_report.minutes_per_week,
        back_to_back_count=load_report.back_to_back_count,
        age=age,
        acute_minutes_7d=float(acute_7d) if acute_7d > 0 else None,
        chronic_minutes_28d_avg=chronic_avg,
    )
    v = result.value
    return {
        "player_external_id": player_external_id,
        "risk_score": v.risk_score,
        "risk_level": v.risk_level,
        "acwr": v.acwr,
        "acwr_flag": v.acwr_flag,
        "factors": {
            "load": v.load_factor,
            "age": v.age_factor,
            "frequency": v.frequency_factor,
        },
        "recommendation": v.recommendation,
        "context": {
            "minutes_per_week": load_report.minutes_per_week,
            "back_to_back_count": load_report.back_to_back_count,
            "window_days": window_days,
        },
    }


# --------------------------------------------------------------------------- #
# 5) Squad depth — pozisyon bazlı derinlik + yaşlanma
# --------------------------------------------------------------------------- #


def tool_get_squad_depth(
    session: Session, *,
    team_external_id: int,
    squad: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Pozisyon bazlı kadro derinliği. Squad parametresi (position+age ile)
    önerilir; verilmezse appearance'tan stub (pozisyon yok → çoğu pozisyon
    `insufficient` görünür)."""
    from app.engine.squad_depth import compute_squad_depth
    if squad is None:
        pids = _team_player_ids(session, team_external_id)
        if not pids:
            return {"info": "appearance verisi yok ve squad parametresi verilmedi"}
        squad = [{"player_id": pid, "position": None, "age": None} for pid in pids]
    result = compute_squad_depth(team_external_id, squad)
    v = result.value
    return {
        "team_external_id": team_external_id,
        "total_players": v.total_players,
        "weakest_position": v.weakest_position,
        "aging_positions": list(v.aging_positions),
        "by_position": [
            {
                "position": p.position,
                "player_count": p.player_count,
                "avg_age": p.avg_age,
                "aging_count": p.aging_count,
                "min_required": p.min_required,
                "depth_status": p.depth_status,
                "aging_risk": p.aging_risk,
            }
            for p in v.by_position
        ],
    }


# --------------------------------------------------------------------------- #
# 6) Rotation plan — yoğun fikstürde dinlendirme önerisi
# --------------------------------------------------------------------------- #


def tool_get_rotation_plan(
    session: Session, *,
    team_external_id: int,
    upcoming_matches: int = 0,
    dense_schedule: bool = False,
    window_days: int = 14,
) -> dict[str, Any]:
    """Rotasyon önerisi — dinlendirilecek oyuncu + öncelik + yoğunluk."""
    from app.engine.rotation_plan import compute_rotation_plan
    loads = _build_team_player_loads(
        session, team_external_id, window_days=window_days,
    )
    if not loads:
        return {"info": "appearance verisi yok"}
    result = compute_rotation_plan(
        team_external_id, loads,
        upcoming_matches=upcoming_matches,
        dense_schedule=dense_schedule,
    )
    v = result.value
    return {
        "team_external_id": team_external_id,
        "upcoming_matches": v.upcoming_matches,
        "dense_schedule": v.dense_schedule,
        "rotate_count": v.rotate_count,
        "rotation_intensity": v.rotation_intensity,
        "candidates": [
            {
                "player_id": c.player_external_id,
                "rest_priority": c.rest_priority,
                "risk_level": c.risk_level,
                "minutes_per_week": c.minutes_per_week,
                "reason": c.reason,
            }
            for c in v.candidates
        ],
    }


# --------------------------------------------------------------------------- #
# Tool schemas — Claude messages.create format
# --------------------------------------------------------------------------- #


V3_TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "get_proactive_alerts",
        "description": (
            "Takımın proaktif uyarıları (yük + sıklık + sözleşme): kritik / "
            "uyarı sayısı + uyarı listesi. Takım kadrosu DB'deki "
            "PlayerAppearance'tan otomatik çıkar."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "team_external_id": {"type": "integer"},
                "upcoming_count": {"type": "integer", "default": 0},
                "dense_schedule": {"type": "boolean", "default": False},
                "horizon_days": {"type": "integer", "default": 14},
            },
            "required": ["team_external_id"],
        },
    },
    {
        "name": "get_matchup_grid",
        "description": (
            "Bir maç için kanal bazlı eşleşme matrisi (sol/orta/sağ). Bizim "
            "atak gücü × rakip savunma zayıflığı → best/worst kanal + tavsiye."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "my_team_external_id": {"type": "integer"},
                "opponent_team_external_id": {"type": "integer"},
                "last_n": {"type": "integer", "default": 5},
            },
            "required": ["my_team_external_id", "opponent_team_external_id"],
        },
    },
    {
        "name": "get_available_squad",
        "description": (
            "Müsait kadro ön-filtresi: sakat/cezalı/aşırı yüklü oyuncu ayrımı. "
            "Squad parametresi verilirse `[{player_id, position?, injured?, "
            "suspended?, risk_level?}]` formatında; yoksa appearance + yük "
            "seviyesinden otomatik üretilir (sakatlık/ceza bilinmediği için "
            "sadece yük doubtful'u görülür)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "team_external_id": {"type": "integer"},
                "squad": {
                    "type": "array",
                    "items": {"type": "object"},
                },
                "window_days": {"type": "integer", "default": 14},
            },
            "required": ["team_external_id"],
        },
    },
    {
        "name": "get_injury_risk",
        "description": (
            "Tek oyuncu için 0-100 sakatlık riski (Gabbett ACWR + yaş + sıklık). "
            "Appearance'tan acute/chronic minute hesaplanır; yaş opsiyonel."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "player_external_id": {"type": "integer"},
                "age": {"type": "integer"},
                "window_days": {"type": "integer", "default": 14},
            },
            "required": ["player_external_id"],
        },
    },
    {
        "name": "get_squad_depth",
        "description": (
            "Pozisyon (G/D/M/F) bazlı kadro derinliği + yaşlanma riski. "
            "Anlamlı sonuç için `squad: [{player_id, position, age?}]` önerilir; "
            "yoksa appearance'tan stub (pozisyon yok → insufficient görünür)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "team_external_id": {"type": "integer"},
                "squad": {
                    "type": "array",
                    "items": {"type": "object"},
                },
            },
            "required": ["team_external_id"],
        },
    },
    {
        "name": "get_rotation_plan",
        "description": (
            "Yoğun fikstürde dinlendirilecek oyuncular + öncelik sırası + "
            "rotasyon yoğunluğu (minimal/moderate/aggressive). Takım yükleri "
            "DB'den otomatik çıkar."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "team_external_id": {"type": "integer"},
                "upcoming_matches": {"type": "integer", "default": 0},
                "dense_schedule": {"type": "boolean", "default": False},
                "window_days": {"type": "integer", "default": 14},
            },
            "required": ["team_external_id"],
        },
    },
]


V3_TOOL_HANDLERS: dict[str, Callable[..., dict[str, Any]]] = {
    "get_proactive_alerts": tool_get_proactive_alerts,
    "get_matchup_grid": tool_get_matchup_grid,
    "get_available_squad": tool_get_available_squad,
    "get_injury_risk": tool_get_injury_risk,
    "get_squad_depth": tool_get_squad_depth,
    "get_rotation_plan": tool_get_rotation_plan,
}
