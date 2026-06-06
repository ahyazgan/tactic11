"""Fiziksel performans testi endpoint'leri.

POST   /physical-tests/                — test kaydı gir
GET    /physical-tests/{player_id}     — oyuncunun tüm testleri (en yeni önce)
GET    /physical-tests/{player_id}/risk  — yükleme riski raporu
GET    /physical-tests/{player_id}/trend?protocol=… — protokol zaman serisi
DELETE /physical-tests/{test_id}       — kaydı sil

Tenant izolasyonu manuel: bu model otomatik tenant-filter kapsamı dışında
olduğundan her sorgu `tenant_id == current_user.tenant_id` ile sınırlanır ve
insert'te tenant_id açıkça set edilir.

KVKK: fiziksel test 'özel nitelikli kişisel veri' → her erişim DataAccessLog'a
işlenir (record_data_access). Yeni ölçüm oyuncuyu 'Kritik' riske taşırsa
yapılandırılmış bildirim kanalına uyarı gider (best-effort).
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.logging import get_logger
from app.db import models
from app.db.physical_test import PhysicalTest, TestProtocol
from app.db.session import get_session
from app.engine.physical.load_risk import (
    CRITICAL_LABEL,
    LoadRiskReport,
    compute_load_risk,
    compute_protocol_trend,
    format_critical_alert,
)

log = get_logger(__name__)

router = APIRouter(prefix="/physical-tests", tags=["physical-tests"])


# ── Pydantic Şemaları ────────────────────────────────────────────────────────

class PhysicalTestCreate(BaseModel):
    player_id: str = Field(..., description="API-Football player ID")
    player_name: str = Field(..., description="Oyuncu adı")
    test_date: date = Field(..., description="Test tarihi")
    protocol: TestProtocol = Field(..., description="Test protokolü")
    value: float = Field(..., description="Ölçülen değer")
    unit: str | None = Field(None, description="Birim (boşsa otomatik doldurulur)")
    notes: str | None = Field(None)
    recorded_by: str | None = Field(None, description="Kaydı yapan kişi")


class PhysicalTestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    player_id: str
    player_name: str
    test_date: date
    protocol: TestProtocol
    value: float
    unit: str | None
    notes: str | None
    recorded_by: str | None


class LoadRiskOut(BaseModel):
    player_id: str
    player_name: str
    risk_score: float
    risk_label: str
    flags: list[dict]
    summary: str
    recommendations: list[str]


class PlayerSummaryOut(BaseModel):
    player_id: str
    player_name: str
    test_count: int
    latest_test_date: date | None
    risk_label: str
    risk_score: float


class TrendOut(BaseModel):
    player_id: str
    protocol: TestProtocol
    direction: str           # improving | worsening | stable | insufficient
    slope: float
    lower_is_better: bool
    points: list[dict]       # [{"test_date": str, "value": float}]


def _log_access(
    session: Session, *, player_id: str, action: str, endpoint: str,
    user_id: str | None = None,
) -> None:
    """KVKK denetim izi — fiziksel test 'özel nitelikli kişisel veri'.

    Hangi oyuncu (subject_id) + HANGI kullanıcı (user_id) erişti kaydedilir.
    subject_id Integer beklediğinden yalnız sayısal player_id'lerde loglanır
    (API-Football id'leri sayısaldır). Hata-toleranslı (record_data_access)."""
    if not player_id.isdigit():
        return
    try:
        from app.api.admin import record_data_access
        record_data_access(
            session, subject_id=int(player_id), user_id=user_id,
            data_category="performance_test", action=action, endpoint=endpoint,
        )
    except Exception as e:  # noqa: BLE001 — denetim logu asıl isteği bozmamalı
        log.warning("KVKK erişim logu yazılamadı: %s", e)


def _maybe_alert_critical(report: LoadRiskReport) -> None:
    """Risk 'Kritik' ise yapılandırılmış kanala uyarı gönder (best-effort)."""
    if report.risk_label != CRITICAL_LABEL:
        return
    try:
        from app.notifications import build_default_notifier
        notifier = build_default_notifier()
        if not notifier.active_channel_names():
            return
        notifier.send_all(format_critical_alert(report))
    except Exception as e:  # noqa: BLE001 — bildirim asıl isteği bozmamalı
        log.warning("kritik risk bildirimi gönderilemedi: %s", e)


def _player_risk(
    session: Session, *, tenant_id: str | None, player_id: str,
) -> LoadRiskReport | None:
    """Oyuncunun son testlerinden risk raporu (kayıt yoksa None)."""
    rows = list(
        session.execute(
            select(PhysicalTest)
            .where(
                PhysicalTest.tenant_id == tenant_id,
                PhysicalTest.player_id == player_id,
            )
            .order_by(PhysicalTest.test_date.desc())
            .limit(20)
        ).scalars()
    )
    if not rows:
        return None
    tests = [
        {
            "protocol": r.protocol, "value": r.value,
            "unit": r.unit, "test_date": r.test_date,
        }
        for r in rows
    ]
    return compute_load_risk(player_id, rows[0].player_name, tests)


# Protokol → otomatik birim eşlemesi.
UNIT_MAP = {
    TestProtocol.SPRINT_10M: "sn",
    TestProtocol.SPRINT_30M: "sn",
    TestProtocol.YOYO_IRL1: "seviye",
    TestProtocol.YOYO_IRL2: "seviye",
    TestProtocol.CMJ: "cm",
    TestProtocol.SJ: "cm",
    TestProtocol.ISOKINETIC_Q: "Nm/kg",
    TestProtocol.ISOKINETIC_H: "Nm/kg",
    TestProtocol.VO2MAX: "ml/kg/min",
    TestProtocol.GPS_DISTANCE: "m",
    TestProtocol.GPS_HIRD: "m",
    TestProtocol.GPS_ACC: "adet",
    TestProtocol.BODY_FAT: "%",
}


# ── Endpoint'ler ─────────────────────────────────────────────────────────────

@router.post("/", response_model=PhysicalTestOut, status_code=status.HTTP_201_CREATED)
def create_test(
    payload: PhysicalTestCreate,
    session: Session = Depends(get_session),
    user: models.User = Depends(get_current_user),
) -> PhysicalTest:
    """Saha test sonucunu kaydet."""
    unit = payload.unit or UNIT_MAP.get(payload.protocol, "")
    record = PhysicalTest(
        tenant_id=user.tenant_id,
        player_id=payload.player_id,
        player_name=payload.player_name,
        test_date=payload.test_date,
        protocol=payload.protocol.value,
        value=payload.value,
        unit=unit,
        notes=payload.notes,
        recorded_by=payload.recorded_by or user.email,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    _log_access(
        session, player_id=record.player_id, action="create",
        endpoint="/physical-tests/", user_id=user.id,
    )
    # Yeni ölçüm oyuncuyu kritik riske taşıdıysa uyar (event-driven).
    report = _player_risk(
        session, tenant_id=user.tenant_id, player_id=record.player_id,
    )
    if report is not None:
        _maybe_alert_critical(report)
    return record


@router.get("/players", response_model=list[PlayerSummaryOut])
def list_players(
    session: Session = Depends(get_session),
    user: models.User = Depends(get_current_user),
) -> list[PlayerSummaryOut]:
    """Tenant'taki test kaydı olan oyuncuların özeti (kadro listesi için).

    NOT: `/{player_id}` ucundan ÖNCE tanımlı olmalı (yoksa 'players' bir
    player_id sanılır)."""
    stmt = (
        select(
            PhysicalTest.player_id,
            func.max(PhysicalTest.player_name),
            func.count(PhysicalTest.id),
            func.max(PhysicalTest.test_date),
        )
        .where(PhysicalTest.tenant_id == user.tenant_id)
        .group_by(PhysicalTest.player_id)
    )
    out: list[PlayerSummaryOut] = []
    for row in session.execute(stmt).all():
        pid = row[0]
        report = _player_risk(session, tenant_id=user.tenant_id, player_id=pid)
        out.append(PlayerSummaryOut(
            player_id=pid,
            player_name=row[1],
            test_count=row[2],
            latest_test_date=row[3],
            risk_label=report.risk_label if report is not None else "Veri Yok",
            risk_score=report.risk_score if report is not None else 0.0,
        ))
    # En riskli üstte (skora göre azalan).
    out.sort(key=lambda p: p.risk_score, reverse=True)
    return out


@router.get("/{player_id}", response_model=list[PhysicalTestOut])
def list_tests(
    player_id: str,
    session: Session = Depends(get_session),
    user: models.User = Depends(get_current_user),
) -> list[PhysicalTest]:
    """Oyuncunun tüm test kayıtlarını getir (en yeni önce)."""
    rows = list(
        session.execute(
            select(PhysicalTest)
            .where(
                PhysicalTest.tenant_id == user.tenant_id,
                PhysicalTest.player_id == player_id,
            )
            .order_by(PhysicalTest.test_date.desc())
        ).scalars()
    )
    if rows:
        _log_access(
            session, player_id=player_id, action="read",
            endpoint="/physical-tests/{player_id}", user_id=user.id,
        )
    return rows


@router.get("/{player_id}/risk", response_model=LoadRiskOut)
def get_risk(
    player_id: str,
    session: Session = Depends(get_session),
    user: models.User = Depends(get_current_user),
) -> LoadRiskOut:
    """Oyuncunun son testlerinden yükleme riski raporu üret."""
    report = _player_risk(session, tenant_id=user.tenant_id, player_id=player_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"player_id={player_id} için test kaydı bulunamadı.",
        )
    _log_access(
        session, player_id=player_id, action="read",
        endpoint="/physical-tests/{player_id}/risk", user_id=user.id,
    )

    return LoadRiskOut(
        player_id=report.player_id,
        player_name=report.player_name,
        risk_score=report.risk_score,
        risk_label=report.risk_label,
        flags=report.flags,
        summary=report.summary,
        recommendations=report.recommendations,
    )


@router.get("/{player_id}/trend", response_model=TrendOut)
def get_trend(
    player_id: str,
    protocol: TestProtocol,
    session: Session = Depends(get_session),
    user: models.User = Depends(get_current_user),
) -> TrendOut:
    """Bir protokolün zaman serisi + eğim/yön (gerileme erken uyarısı)."""
    rows = list(
        session.execute(
            select(PhysicalTest)
            .where(
                PhysicalTest.tenant_id == user.tenant_id,
                PhysicalTest.player_id == player_id,
                PhysicalTest.protocol == protocol.value,
            )
            .order_by(PhysicalTest.test_date.asc())
        ).scalars()
    )
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{player_id} / {protocol.value} için ölçüm yok.",
        )
    _log_access(
        session, player_id=player_id, action="read",
        endpoint="/physical-tests/{player_id}/trend", user_id=user.id,
    )
    points = [{"test_date": r.test_date, "value": r.value} for r in rows]
    trend = compute_protocol_trend(protocol.value, points)
    return TrendOut(
        player_id=player_id,
        protocol=protocol,
        direction=trend.direction,
        slope=trend.slope,
        lower_is_better=trend.lower_is_better,
        points=trend.points,
    )


@router.delete("/{test_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_test(
    test_id: int,
    session: Session = Depends(get_session),
    user: models.User = Depends(get_current_user),
) -> None:
    """Test kaydını sil (sadece aynı tenant)."""
    row = session.execute(
        select(PhysicalTest).where(
            PhysicalTest.id == test_id,
            PhysicalTest.tenant_id == user.tenant_id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Kayıt bulunamadı.")
    player_id = row.player_id
    session.delete(row)
    session.commit()
    _log_access(
        session, player_id=player_id, action="delete",
        endpoint="/physical-tests/{test_id}", user_id=user.id,
    )
