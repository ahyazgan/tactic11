"""Live Alerts — maç-içi proaktif uyarı motoru (J, saf).

Mevcut `proactive_alerts` maç-ÖNCESİ yük/fikstür uyarısı verir. Bu engine
maç-İÇİ: canlı snapshot sinyalleri eşik aştığında önceliklendirilmiş, eyleme
dönük uyarı üretir — sistemi "sorulunca cevaplayan"dan "aktif uyaran"a çevirir.
Her uyarının `dedup_key`'i vardır; çağıran (WS katmanı) aynı uyarıyı her
snapshot'ta tekrar push etmesin diye.

Saf: durum girdileri → uyarı listesi. Push/e-posta GÖNDERİMİ ayrı (infra);
burası yalnız "ne zaman, neyi" kararı.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

ENGINE_NAME = "engine.live_alerts"
ENGINE_VERSION = "1"

# Yük (fatigue 0..1) eşikleri.
FATIGUE_WARN = 0.80
FATIGUE_CRIT = 0.90
# Düello kayıp oranı (0..1) — kart/eşleşme riski için.
DUEL_LOSS_HIGH = 0.6
# Momentum bize karşı kaç snapshot sürerse uyarı.
MOMENTUM_SUSTAINED_WARN = 2
MOMENTUM_SUSTAINED_CRIT = 3

_SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}


@dataclass(frozen=True)
class LiveAlert:
    alert_type: str               # momentum_break | fatigue | card_risk | data_quality
    severity: str                 # critical | warning | info
    message: str
    dedup_key: str                # aynı uyarıyı tekrar push etmemek için
    player_external_id: int | None = None


@dataclass(frozen=True)
class LiveAlertsReport:
    current_minute: float
    total: int
    critical: int
    warning: int
    info: int
    alerts: tuple[LiveAlert, ...] = field(default_factory=tuple)


def compute_live_alerts(
    *,
    current_minute: float,
    momentum_trend: dict[str, Any] | None = None,
    player_states: list[dict[str, Any]] | None = None,
    data_quality_status: str | None = None,
) -> LiveAlertsReport:
    """Canlı durumdan proaktif uyarılar üret.

    momentum_trend: summarize_trend çıktısı ({"momentum": {direction, sustained_snapshots}}).
    player_states: [{player_id, fatigue?, yellow_card?, duel_loss_rate?}].
    data_quality_status: "ok"|"degraded"|"poor".
    """
    alerts: list[LiveAlert] = []

    # Momentum kırılması (bize karşı, sürekli)
    mom = (momentum_trend or {}).get("momentum") or {}
    if mom.get("direction") == "rakibe doğru":
        sustained = int(mom.get("sustained_snapshots", 0))
        if sustained >= MOMENTUM_SUSTAINED_CRIT:
            alerts.append(LiveAlert(
                alert_type="momentum_break", severity="critical",
                message=(f"Momentum {sustained} snapshot'tır rakibe — acil "
                         "müdahale (değişiklik/taktik) düşün"),
                dedup_key="momentum_break",
            ))
        elif sustained >= MOMENTUM_SUSTAINED_WARN:
            alerts.append(LiveAlert(
                alert_type="momentum_break", severity="warning",
                message=f"Momentum {sustained} snapshot'tır rakibe kayıyor — izle",
                dedup_key="momentum_break",
            ))

    # Oyuncu bazlı: yük + kart riski
    for ps in (player_states or []):
        pid = ps.get("player_id")
        fatigue = float(ps.get("fatigue", 0.0))
        if fatigue >= FATIGUE_CRIT:
            alerts.append(LiveAlert(
                alert_type="fatigue", severity="critical",
                message=f"#{pid} yük kritik (%{int(fatigue*100)}) — değiştir",
                dedup_key=f"fatigue:{pid}", player_external_id=pid,
            ))
        elif fatigue >= FATIGUE_WARN:
            alerts.append(LiveAlert(
                alert_type="fatigue", severity="warning",
                message=f"#{pid} yük yüksek (%{int(fatigue*100)}) — değişiklik hazırla",
                dedup_key=f"fatigue:{pid}", player_external_id=pid,
            ))
        # Kart sınırı: sarı + yüksek düello kaybı → ikinci sarı riski
        if ps.get("yellow_card") and float(ps.get("duel_loss_rate", 0.0)) >= DUEL_LOSS_HIGH:
            alerts.append(LiveAlert(
                alert_type="card_risk", severity="critical",
                message=f"#{pid} sarı kartlı + düello kaybediyor — ikinci sarı riski",
                dedup_key=f"card:{pid}", player_external_id=pid,
            ))

    # Veri kalitesi düşükse: uyarıları temkinli yorumla (info)
    if data_quality_status == "poor":
        alerts.append(LiveAlert(
            alert_type="data_quality", severity="info",
            message="Veri kalitesi düşük — uyarılar temkinli değerlendirilmeli",
            dedup_key="data_quality_poor",
        ))

    alerts.sort(key=lambda a: _SEVERITY_ORDER.get(a.severity, 9))
    return LiveAlertsReport(
        current_minute=current_minute,
        total=len(alerts),
        critical=sum(1 for a in alerts if a.severity == "critical"),
        warning=sum(1 for a in alerts if a.severity == "warning"),
        info=sum(1 for a in alerts if a.severity == "info"),
        alerts=tuple(alerts),
    )
