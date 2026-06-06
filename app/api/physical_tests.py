"""Fiziksel performans testi endpoint'leri.

POST   /physical-tests/               — test kaydı gir
GET    /physical-tests/{player_id}    — oyuncunun tüm testleri (en yeni önce)
GET    /physical-tests/{player_id}/risk — yükleme riski raporu
DELETE /physical-tests/{test_id}      — kaydı sil

Tenant izolasyonu manuel: bu model otomatik tenant-filter kapsamı dışında
olduğundan her sorgu `tenant_id == current_user.tenant_id` ile sınırlanır ve
insert'te tenant_id açıkça set edilir.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db import models
from app.db.physical_test import PhysicalTest, TestProtocol
from app.db.session import get_session
from app.engine.physical.load_risk import compute_load_risk

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
    return record


@router.get("/{player_id}", response_model=list[PhysicalTestOut])
def list_tests(
    player_id: str,
    session: Session = Depends(get_session),
    user: models.User = Depends(get_current_user),
) -> list[PhysicalTest]:
    """Oyuncunun tüm test kayıtlarını getir (en yeni önce)."""
    return list(
        session.execute(
            select(PhysicalTest)
            .where(
                PhysicalTest.tenant_id == user.tenant_id,
                PhysicalTest.player_id == player_id,
            )
            .order_by(PhysicalTest.test_date.desc())
        ).scalars()
    )


@router.get("/{player_id}/risk", response_model=LoadRiskOut)
def get_risk(
    player_id: str,
    session: Session = Depends(get_session),
    user: models.User = Depends(get_current_user),
) -> LoadRiskOut:
    """Oyuncunun son testlerinden yükleme riski raporu üret."""
    rows = list(
        session.execute(
            select(PhysicalTest)
            .where(
                PhysicalTest.tenant_id == user.tenant_id,
                PhysicalTest.player_id == player_id,
            )
            .order_by(PhysicalTest.test_date.desc())
            .limit(20)
        ).scalars()
    )

    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"player_id={player_id} için test kaydı bulunamadı.",
        )

    tests = [
        {
            "protocol": r.protocol,
            "value": r.value,
            "unit": r.unit,
            "test_date": r.test_date,
        }
        for r in rows
    ]
    report = compute_load_risk(player_id, rows[0].player_name, tests)

    return LoadRiskOut(
        player_id=report.player_id,
        player_name=report.player_name,
        risk_score=report.risk_score,
        risk_label=report.risk_label,
        flags=report.flags,
        summary=report.summary,
        recommendations=report.recommendations,
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
    session.delete(row)
    session.commit()
