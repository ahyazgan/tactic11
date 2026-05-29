"""Contract Alerts — sözleşme bitişi yaklaşan oyuncu uyarıları (Faz 5 #34).

Sözleşme sona erme tarihi `horizon_days` içindeyse seviyelendirilmiş uyarı:
- critical:  ≤ 60 gün (acil görüşme/karar)
- warning:   ≤ 180 gün (görüşme penceresi)
- notice:    horizon_days içinde geri kalan (planlamaya başla)
- expired:   tarih geçmiş

Saf hesap. DB/ORM bilmez; caller dict listesi gönderir.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from typing import Any

from app.audit import AuditRecord, EngineResult

ENGINE_NAME = "engine.contract_alerts"
ENGINE_VERSION = "1"

CRITICAL_DAYS = 60
WARNING_DAYS = 180


@dataclass(frozen=True)
class ContractAlert:
    player_external_id: int
    contract_end: date
    days_remaining: int          # negatif → expired
    level: str                    # "critical" | "warning" | "notice" | "expired"
    annual_salary_eur: int | None
    message: str


@dataclass(frozen=True)
class ContractAlertsReport:
    team_external_id: int | None
    total_contracts: int
    in_horizon: int
    critical_count: int
    warning_count: int
    notice_count: int
    expired_count: int
    alerts: tuple[ContractAlert, ...]


def _level(days: int) -> str:
    if days < 0:
        return "expired"
    if days <= CRITICAL_DAYS:
        return "critical"
    if days <= WARNING_DAYS:
        return "warning"
    return "notice"


def _message(player_id: int, level: str, days: int) -> str:
    if level == "expired":
        return f"Oyuncu {player_id}: sözleşme {-days} gün önce bitmiş — kayıt güncel mi?"
    if level == "critical":
        return f"Oyuncu {player_id}: {days} gün kaldı — acil görüşme / karar"
    if level == "warning":
        return f"Oyuncu {player_id}: {days} gün kaldı — görüşme açın"
    return f"Oyuncu {player_id}: {days} gün kaldı — planlamaya başlayın"


def compute_contract_alerts(
    contracts: Iterable[dict[str, Any]],
    *,
    today: date,
    horizon_days: int = 365,
    team_external_id: int | None = None,
) -> EngineResult[ContractAlertsReport]:
    """Horizon penceresi içindeki + geçmiş sözleşmelere uyarı üret.

    contracts: [{
        player_external_id: int,
        contract_end: date,
        annual_salary_eur?: int | None,
    }]
    """
    alerts: list[ContractAlert] = []
    total = 0
    for c in contracts:
        total += 1
        end = c.get("contract_end")
        pid = int(c.get("player_external_id", 0))
        if end is None:
            continue
        days = (end - today).days
        # Horizon dışı (gelecekte uzak) — atlanır
        if days > horizon_days:
            continue
        lvl = _level(days)
        alerts.append(ContractAlert(
            player_external_id=pid,
            contract_end=end,
            days_remaining=days,
            level=lvl,
            annual_salary_eur=c.get("annual_salary_eur"),
            message=_message(pid, lvl, days),
        ))

    # Sıralama: critical > expired > warning > notice; içinde days_remaining
    level_order = {"critical": 0, "expired": 1, "warning": 2, "notice": 3}
    alerts.sort(
        key=lambda a: (level_order.get(a.level, 9), a.days_remaining),
    )

    counts = {"critical": 0, "warning": 0, "notice": 0, "expired": 0}
    for a in alerts:
        counts[a.level] += 1

    report = ContractAlertsReport(
        team_external_id=team_external_id,
        total_contracts=total,
        in_horizon=len(alerts),
        critical_count=counts["critical"],
        warning_count=counts["warning"],
        notice_count=counts["notice"],
        expired_count=counts["expired"],
        alerts=tuple(alerts),
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="team", subject_id=team_external_id or 0,
        metric="contract_alerts",
        value={
            "total_contracts": total,
            "in_horizon": len(alerts),
            "critical": counts["critical"],
            "warning": counts["warning"],
            "notice": counts["notice"],
            "expired": counts["expired"],
        },
        inputs={"today": today.isoformat(), "horizon_days": horizon_days},
        formula=(
            f"days_remaining = contract_end - today; "
            f"critical ≤ {CRITICAL_DAYS}; warning ≤ {WARNING_DAYS}; "
            f"horizon_days = {horizon_days}"
        ),
    )
    return EngineResult(value=report, audit=audit)
