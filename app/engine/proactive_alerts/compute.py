"""Proactive Alerts — yük/risk/zaaf uyarı motoru (Faz 5 #14).

TD'nin sabah açtığında "şuna dikkat" diyen uyarı listesi. Saf hesap:
caller player_load raporları + maç durumu + (opsiyonel) sözleşme/yaş
verisi gönderir; biz önceliklendirilmiş alert listesi döneriz.

Alert tipleri:
- high_load: oyuncu yük eşiğini aştı (risk_level high/extreme)
- back_to_back: 5 günde 3+ maç
- fixture_congestion: önümüzdeki N günde yoğun fikstür
- contract_expiry: sözleşme < X ay (caller verirse)
- aging_core: kilit oyuncu yaş > 32 (caller verirse)

Her alert: severity (info/warning/critical) + actionable mesaj.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from app.audit import AuditRecord, EngineResult

ENGINE_NAME = "engine.proactive_alerts"
ENGINE_VERSION = "1"

SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}


@dataclass(frozen=True)
class Alert:
    alert_type: str       # high_load | back_to_back | fixture_congestion | ...
    severity: str         # critical | warning | info
    subject_type: str     # player | team | match
    subject_id: int
    message: str          # human-readable Türkçe
    metric_value: float | None = None


@dataclass(frozen=True)
class ProactiveAlertsReport:
    team_external_id: int
    total_alerts: int
    critical_count: int
    warning_count: int
    alerts: tuple[Alert, ...]   # severity sıralı


def _load_alerts(player_loads: list[dict[str, Any]]) -> list[Alert]:
    """player_load dict'lerinden yük uyarıları."""
    alerts: list[Alert] = []
    for pl in player_loads:
        pid = pl.get("player_external_id", 0)
        risk = pl.get("risk_level", "low")
        mpw = pl.get("minutes_per_week", 0.0)
        b2b = pl.get("back_to_back_count", 0)
        if risk == "extreme":
            alerts.append(Alert(
                alert_type="high_load", severity="critical",
                subject_type="player", subject_id=pid,
                message=(
                    f"Player {pid} EXTREME yük ({mpw:.0f} dk/hafta) — "
                    f"rotasyon/dinlendirme şart"
                ),
                metric_value=mpw,
            ))
        elif risk == "high":
            alerts.append(Alert(
                alert_type="high_load", severity="warning",
                subject_type="player", subject_id=pid,
                message=(
                    f"Player {pid} yüksek yük ({mpw:.0f} dk/hafta) — "
                    f"izlemeye al"
                ),
                metric_value=mpw,
            ))
        if b2b >= 3:
            alerts.append(Alert(
                alert_type="back_to_back", severity="warning",
                subject_type="player", subject_id=pid,
                message=f"Player {pid} 5 günde {b2b} maç — sakatlık riski",
                metric_value=float(b2b),
            ))
    return alerts


def _fixture_alert(
    team_id: int, upcoming_count: int, dense: bool, horizon_days: int,
) -> list[Alert]:
    if dense:
        return [Alert(
            alert_type="fixture_congestion", severity="warning",
            subject_type="team", subject_id=team_id,
            message=(
                f"{horizon_days} günde {upcoming_count} maç — yoğun fikstür, "
                f"rotasyon planla"
            ),
            metric_value=float(upcoming_count),
        )]
    return []


def _contract_age_alerts(
    contract_warnings: list[dict[str, Any]],
) -> list[Alert]:
    """caller verirse sözleşme/yaş uyarıları.

    contract_warnings: [{player_id, months_left?, age?}]
    """
    alerts: list[Alert] = []
    for cw in contract_warnings:
        pid = cw.get("player_id", 0)
        months = cw.get("months_left")
        age = cw.get("age")
        if months is not None and months <= 6:
            alerts.append(Alert(
                alert_type="contract_expiry",
                severity="critical" if months <= 3 else "warning",
                subject_type="player", subject_id=pid,
                message=f"Player {pid} sözleşme {months} ay kaldı — uzatma/satış kararı",
                metric_value=float(months),
            ))
        if age is not None and age >= 32:
            alerts.append(Alert(
                alert_type="aging_core", severity="info",
                subject_type="player", subject_id=pid,
                message=f"Player {pid} yaş {age} — halef planlaması düşün",
                metric_value=float(age),
            ))
    return alerts


def compute_proactive_alerts(
    team_external_id: int,
    *,
    player_loads: Iterable[dict[str, Any]] = (),
    upcoming_count: int = 0,
    dense_schedule: bool = False,
    horizon_days: int = 14,
    contract_warnings: Iterable[dict[str, Any]] = (),
) -> EngineResult[ProactiveAlertsReport]:
    """Tüm uyarı kaynaklarını birleştir, severity sıralı liste döner."""
    alerts: list[Alert] = []
    alerts.extend(_load_alerts(list(player_loads)))
    alerts.extend(_fixture_alert(
        team_external_id, upcoming_count, dense_schedule, horizon_days,
    ))
    alerts.extend(_contract_age_alerts(list(contract_warnings)))

    alerts.sort(key=lambda a: SEVERITY_ORDER.get(a.severity, 9))
    crit = sum(1 for a in alerts if a.severity == "critical")
    warn = sum(1 for a in alerts if a.severity == "warning")

    report = ProactiveAlertsReport(
        team_external_id=team_external_id,
        total_alerts=len(alerts),
        critical_count=crit,
        warning_count=warn,
        alerts=tuple(alerts),
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="team", subject_id=team_external_id,
        metric="proactive_alerts",
        value={
            "total_alerts": len(alerts),
            "critical_count": crit,
            "warning_count": warn,
            "alerts": [
                {"type": a.alert_type, "severity": a.severity,
                 "subject_id": a.subject_id, "message": a.message}
                for a in alerts
            ],
        },
        inputs={
            "horizon_days": horizon_days,
            "upcoming_count": upcoming_count,
            "dense_schedule": dense_schedule,
        },
        formula="load + back_to_back + fixture_congestion + contract/age → severity sorted",
    )
    return EngineResult(value=report, audit=audit)
