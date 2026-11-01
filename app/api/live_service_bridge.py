"""Canlı servis → WS snapshot köprüsü.

Kamera modunda skor videodan okunamaz (gol tespiti yok); servis bağlıysa skor,
olaylar ve sahiplik payı servisten gelir ve snapshot'a `service` bloğu olarak
eklenir. Servisin yeni bildirdiği olaylar (gol, kırmızı kart, değişiklik) panoya
uyarı olarak düşer. Servis hatası snapshot'ı bozmaz: blokta `error` görünür.

Ev/deplasman eşlemesi: servis fikstürü maçın kendisidir; servis `team` 0 = DB'deki
ev sahibi kabul edilir (operatör aynı maçın fikstür kimliğini verir).
"""

from __future__ import annotations

from typing import Any

from app.data.sources.live_service import GOAL_KINDS, LiveServicePoller, ServiceEvent

RECENT_WINDOW_MIN = 10.0


def service_block(poller: LiveServicePoller) -> dict[str, Any] | None:
    snap = poller.snapshot
    if snap is None:
        return {"provider": getattr(poller.service, "provider", None), "status": "waiting",
                "error": poller.last_error}
    window = None
    if snap.minute is not None:
        window = poller.history.window_share(max(0.0, snap.minute - RECENT_WINDOW_MIN), float(snap.minute))
    return {
        "provider": snap.provider, "fixture_id": snap.fixture_id, "status": snap.status,
        "minute": snap.minute, "score": list(snap.score),
        "possession_total": list(snap.possession) if snap.possession else None,
        # son 10 dk'da ev sahibinin sahiplik payı (birikmiş yüzdelerden); kısa geçmişte None
        "possession_last_10_home": window,
        "events": [_event_dict(e) for e in snap.events],
        "period_starts": [t.isoformat() for t in snap.period_starts],
        "fetched_at": snap.fetched_at.isoformat(), "error": poller.last_error,
    }


def _event_dict(e: ServiceEvent) -> dict[str, Any]:
    return {"kind": e.kind, "minute": e.minute, "extra_minute": e.extra_minute, "team": e.team,
            "player": e.player, "related_player": e.related_player}


def _who(team: int | None, my_side: int | None) -> str:
    if team is None or my_side is None:
        return ""
    return "Biz" if team == my_side else "Rakip"


def service_alerts(fresh: list[ServiceEvent], my_side: int | None) -> list[dict[str, Any]]:
    """Servisin bu turda ilk kez bildirdiği olaylardan pano uyarıları."""
    out: list[dict[str, Any]] = []
    for e in fresh:
        who = _who(e.team, my_side)
        minute = f"{e.minute}+{e.extra_minute}'" if e.extra_minute else f"{e.minute}'"
        if e.kind in GOAL_KINDS:
            text = "kendi kalesine" if e.kind == "own_goal" else "gol"
            sev, msg = "warning", f"{minute} {who} {text}: {e.player or '?'}".replace("  ", " ")
        elif e.kind == "red":
            sev, msg = "critical", f"{minute} {who} kırmızı kart: {e.player or '?'} — sayı dengesi değişti"
        elif e.kind == "substitution":
            sev, msg = "info", f"{minute} {who} değişiklik: {e.player or '?'} girdi, {e.related_player or '?'} çıktı"
        elif e.kind == "yellow":
            sev, msg = "info", f"{minute} {who} sarı kart: {e.player or '?'}"
        else:
            continue
        out.append({"type": f"service_{e.kind}", "severity": sev, "message": msg.strip(),
                    "dedup_key": f"service:{e.kind}:{e.minute}:{e.extra_minute}:{e.player}",
                    "player_id": None})
    return out


def merge_alerts(live_alerts: dict[str, Any], extra: list[dict[str, Any]]) -> None:
    """`snapshot['live_alerts']` bloğuna ek uyarıları sayılarıyla birlikte ekle."""
    if not extra:
        return
    order = {"critical": 0, "warning": 1, "info": 2}
    alerts = sorted([*live_alerts.get("alerts", []), *extra], key=lambda a: order.get(a["severity"], 9))
    live_alerts["alerts"] = alerts
    live_alerts["total"] = len(alerts)
    for sev in ("critical", "warning", "info"):
        live_alerts[sev] = sum(1 for a in alerts if a["severity"] == sev)
