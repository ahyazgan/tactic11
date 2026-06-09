"""Fiziksel performans testi endpoint'leri.

POST   /physical-tests/                — test kaydı gir
POST   /physical-tests/batch           — toplu kayıt (bir protokol, çok oyuncu)
GET    /physical-tests/protocols       — tüm protokollerin tanımı + nasıl-yapılır
GET    /physical-tests/{player_id}     — oyuncunun tüm testleri (en yeni önce)
GET    /physical-tests/{player_id}/risk  — yükleme riski raporu
GET    /physical-tests/{player_id}/battery — test günü profili + SWC yorumu
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

from dataclasses import asdict
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.logging import get_logger
from app.db import models
from app.db.physical_test import PhysicalTest, TestProtocol
from app.db.session import get_session
from app.engine.performance_test import compute as perf
from app.engine.physical.load_risk import (
    CRITICAL_LABEL,
    REFERENCE,
    LoadRiskReport,
    compute_load_risk,
    compute_protocol_trend,
    format_critical_alert,
    rate_against_norms,
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
    components: dict[str, Any] | None = Field(
        None, description="Ham bileşenler (RSA süreleri, DJ uçuş/temas, hop sol/sağ vb.)",
    )


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
    components: dict[str, Any] | None = None
    # Norm derecesi (elit/iyi/ortalama/zayıf) — eski batarya sisteminden, B'ye
    # taşındı. from_attributes ile alanlar dolduktan sonra hesaplanır.
    rating: str | None = None

    @model_validator(mode="after")
    def _fill_rating(self) -> PhysicalTestOut:
        self.rating = rate_against_norms(self.protocol.value, self.value)
        return self


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
    TestProtocol.TTEST_AGILITY: "sn",
    TestProtocol.RSA: "sn",
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
    TestProtocol.SPRINT_5M: "sn",
    TestProtocol.T505: "sn",
    TestProtocol.ARROWHEAD: "sn",
    TestProtocol.ILLINOIS: "sn",
    TestProtocol.IFT_30_15: "km/sa",
    TestProtocol.ADDUCTOR_SQUEEZE: "N",
    TestProtocol.DROP_JUMP_RSI: "RSI",
    TestProtocol.TRIPLE_HOP: "cm",
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
        components=payload.components,
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


class ProtocolInfoOut(BaseModel):
    key: str
    name: str
    unit: str
    higher_is_better: bool
    description: str
    norm_elite: float
    norm_good: float
    norm_average: float
    # load_risk REFERENCE'tan: referans aralığı (varsa)
    ref_low: float | None = None
    ref_high: float | None = None


@router.get("/protocols", response_model=list[ProtocolInfoOut])
def list_protocols(position: str | None = None) -> list[ProtocolInfoOut]:
    """Desteklenen test protokollerinin tanımı, nasıl-yapılır metni ve norm eşikleri.

    `?position=` verilirse (TR ya da EN kod: GK/CM/WB_W/kaleci…) yalnız o mevkinin
    önerilen test paketi döner. Auth gerektirmez — tester tableti için herkese açık.

    NOT: `/{player_id}` ucundan ÖNCE tanımlı olmalı (yoksa 'protocols' bir
    player_id sanılır)."""
    allowed = set(perf.protocols_for_position(position)) if position else None
    out: list[ProtocolInfoOut] = []
    for key, proto in perf.PROTOCOLS.items():
        if key == "custom":
            continue
        if allowed is not None and key not in allowed:
            continue
        norms = dict(proto.norm_cutoffs)   # {"elit": x, "iyi": y, "ortalama": z}
        ref = REFERENCE.get(key)
        out.append(ProtocolInfoOut(
            key=proto.key,
            name=proto.name,
            unit=proto.unit,
            higher_is_better=proto.higher_is_better,
            description=proto.description,
            norm_elite=norms["elit"],
            norm_good=norms["iyi"],
            norm_average=norms["ortalama"],
            ref_low=float(ref["low"]) if ref is not None else None,
            ref_high=float(ref["high"]) if ref is not None else None,
        ))
    out.sort(key=lambda p: p.key)
    return out


# ── Türetilmiş metrik hesaplama uçları (saf, auth'suz — tester tableti) ──────
# Ham ölçümleri alır, spor-bilimi göstergesi döner. DB'ye dokunmaz; istenirse
# sonuç POST /physical-tests/ ile `components` alanına yazılarak saklanır.

def _derive_or_422(fn: Any, *args: Any, **kwargs: Any) -> Any:
    """Engine saf fonksiyonunu çağır; geçersiz girdi (ValueError) → 422."""
    try:
        return fn(*args, **kwargs)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=str(e)) from e


class RSAFatigueIn(BaseModel):
    sprint_times: list[float] = Field(..., min_length=2, max_length=20,
                                      description="Sprint süreleri (sn), kronolojik")


class RSAFatigueOut(BaseModel):
    n: int
    best: float
    mean: float
    total: float
    fatigue_index_pct: float
    insufficient_recovery: bool
    note: str


@router.post("/derive/rsa-fatigue", response_model=RSAFatigueOut)
def derive_rsa_fatigue(payload: RSAFatigueIn) -> RSAFatigueOut:
    """Tekrarlı sprint sürelerinden Yorgunluk İndeksi (FI>%7 → yetersiz toparlanma)."""
    r = _derive_or_422(perf.repeated_sprint_fatigue_index, payload.sprint_times)
    return RSAFatigueOut(**asdict(r))


class CODDeficitIn(BaseModel):
    cod_time: float = Field(..., gt=0, description="505 (veya COD) süresi, sn")
    linear_10m: float = Field(..., gt=0, description="10m düz sprint süresi, sn")


class CODDeficitOut(BaseModel):
    cod_time: float
    linear_time: float
    deficit: float
    poor_deceleration: bool
    note: str


@router.post("/derive/cod-deficit", response_model=CODDeficitOut)
def derive_cod_deficit(payload: CODDeficitIn) -> CODDeficitOut:
    """COD Deficit = 505 − 10m düz sprint (yüksek → zayıf frenleme/deceleration)."""
    r = _derive_or_422(perf.change_of_direction_deficit,
                       payload.cod_time, payload.linear_10m)
    return CODDeficitOut(**asdict(r))


class RSIIn(BaseModel):
    flight_time_s: float = Field(..., ge=0, description="Havada kalma süresi, sn")
    contact_time_s: float = Field(..., gt=0, description="Yere temas süresi, sn")


class RSIOut(BaseModel):
    rsi: float


@router.post("/derive/rsi", response_model=RSIOut)
def derive_rsi(payload: RSIIn) -> RSIOut:
    """Drop Jump RSI = uçuş süresi / temas süresi (reaktif kuvvet)."""
    rsi = _derive_or_422(perf.reactive_strength_index,
                         payload.flight_time_s, payload.contact_time_s)
    return RSIOut(rsi=rsi)


class AsymmetryIn(BaseModel):
    left: float = Field(..., ge=0, description="Sol bacak ölçümü")
    right: float = Field(..., ge=0, description="Sağ bacak ölçümü")


class AsymmetryOut(BaseModel):
    left: float
    right: float
    asymmetry_pct: float
    stronger_side: str
    flag: str
    note: str


@router.post("/derive/asymmetry", response_model=AsymmetryOut)
def derive_asymmetry(payload: AsymmetryIn) -> AsymmetryOut:
    """Bacak asimetri %'si + bayrak (>%10 sarı, >%15 kırmızı). Triple Hop vb."""
    r = _derive_or_422(perf.limb_asymmetry, payload.left, payload.right)
    return AsymmetryOut(**asdict(r))


class VO2YoyoIn(BaseModel):
    distance_m: float = Field(..., ge=0, description="Yo-Yo IR1 toplam mesafe (m)")


class VO2VIFTIn(BaseModel):
    vift_kmh: float = Field(..., gt=0, description="30-15 IFT son kademe hızı (km/sa)")
    age: int = Field(..., gt=0, lt=60)
    weight_kg: float = Field(..., gt=0)
    female: bool = Field(False)


class VO2Out(BaseModel):
    vo2max: float = Field(..., description="Kestirilen VO2max (ml/kg/dk)")


@router.post("/derive/vo2max/yoyo", response_model=VO2Out)
def derive_vo2max_yoyo(payload: VO2YoyoIn) -> VO2Out:
    """Yo-Yo IR1 mesafesinden VO2max kestirimi — Bangsbo (2008)."""
    v = _derive_or_422(perf.derive_vo2max_from_yoyo_ir1, payload.distance_m)
    return VO2Out(vo2max=v)


@router.post("/derive/vo2max/vift", response_model=VO2Out)
def derive_vo2max_vift(payload: VO2VIFTIn) -> VO2Out:
    """VIFT (30-15 IFT) + yaş/kilo/cinsiyetten VO2max kestirimi — Buchheit (2008)."""
    v = _derive_or_422(perf.estimate_vo2max_from_vift, payload.vift_kmh,
                       payload.age, payload.weight_kg, female=payload.female)
    return VO2Out(vo2max=v)


class DropChangeOut(BaseModel):
    current: float
    previous: float
    drop_pct: float
    flagged: bool
    note: str


class AdductorDropIn(BaseModel):
    current: float = Field(..., ge=0, description="Güncel adductor squeeze (N)")
    previous: float = Field(..., gt=0, description="Önceki ölçüm (N)")


@router.post("/derive/adductor-drop", response_model=DropChangeOut)
def derive_adductor_drop(payload: AdductorDropIn) -> DropChangeOut:
    """MD+1 Adductor Squeeze düşüşü (>%10 → kasık/pubis riski)."""
    r = _derive_or_422(perf.adductor_squeeze_drop, payload.current, payload.previous)
    return DropChangeOut(**asdict(r))


class CMJFatigueIn(BaseModel):
    current: float = Field(..., ge=0, description="Güncel CMJ (cm)")
    baseline_values: list[float] = Field(..., min_length=1,
                                         description="Baseline CMJ ölçümleri (cm)")


@router.post("/derive/cmj-fatigue", response_model=DropChangeOut)
def derive_cmj_fatigue(payload: CMJFatigueIn) -> DropChangeOut:
    """MD+1 CMJ baseline kıyas (>%10 düşüş → nöromusküler yorgunluk)."""
    r = _derive_or_422(perf.cmj_neuromuscular_drop, payload.current,
                       payload.baseline_values)
    return DropChangeOut(**asdict(r))


class ReturnToPlayIn(BaseModel):
    current: float = Field(..., gt=0, description="Dönüş mikro-test sonucu")
    pre_injury_baseline: float = Field(..., gt=0, description="Sakatlık-öncesi baseline")
    higher_is_better: bool = Field(True, description="Metrik yönü (sprint süresi=False)")


class ReturnToPlayOut(BaseModel):
    current: float
    baseline: float
    pct_of_baseline: float
    cleared: bool
    light: str
    note: str


@router.post("/derive/return-to-play", response_model=ReturnToPlayOut)
def derive_return_to_play(payload: ReturnToPlayIn) -> ReturnToPlayOut:
    """Return-to-play: baseline'a göre <%95 kırmızı / ≥%95 yeşil ışık."""
    r = _derive_or_422(perf.return_to_play_readiness, payload.current,
                       payload.pre_injury_baseline,
                       higher_is_better=payload.higher_is_better)
    return ReturnToPlayOut(**asdict(r))


class HQRatioIn(BaseModel):
    hamstring: float = Field(..., ge=0, description="İzokinetik hamstring tepe tork")
    quadriceps: float = Field(..., gt=0, description="İzokinetik quadriceps tepe tork")


class HQRatioOut(BaseModel):
    hamstring: float
    quadriceps: float
    ratio: float
    band: str
    at_risk: bool
    note: str


@router.post("/derive/hq-ratio", response_model=HQRatioOut)
def derive_hq_ratio(payload: HQRatioIn) -> HQRatioOut:
    """Hamstring:Quadriceps oranı + risk bandı (<0.47 yüksek hamstring riski)."""
    r = _derive_or_422(perf.hamstring_quad_ratio, payload.hamstring, payload.quadriceps)
    return HQRatioOut(**asdict(r))


class SprintSplitIn(BaseModel):
    t5: float | None = Field(None, gt=0, description="0-5m süresi (sn)")
    t10: float | None = Field(None, gt=0, description="0-10m süresi (sn)")
    t30: float | None = Field(None, gt=0, description="0-30m süresi (sn)")


class SprintSplitOut(BaseModel):
    t5: float | None
    t10: float | None
    t30: float | None
    reaction: float | None
    acceleration: float | None
    max_speed: float | None
    limiter: str
    note: str


@router.post("/derive/sprint-split", response_model=SprintSplitOut)
def derive_sprint_split(payload: SprintSplitIn) -> SprintSplitOut:
    """Sprint split faz analizi (0-5/5-10/10-30m) → limitör faz (reaksiyon/ivmelenme/max hız)."""
    r = _derive_or_422(perf.sprint_split_analysis, payload.t5, payload.t10, payload.t30)
    return SprintSplitOut(**asdict(r))


class VIFTTargetsIn(BaseModel):
    vift: float = Field(..., gt=0, description="30-15 IFT son kademe hızı (km/sa)")


class VIFTTargetsOut(BaseModel):
    vift: float
    speed_95: float
    speed_100: float
    speed_105: float
    note: str


@router.post("/derive/vift-targets", response_model=VIFTTargetsOut)
def derive_vift_targets(payload: VIFTTargetsIn) -> VIFTTargetsOut:
    """VIFT'ten %95/100/105 aerobik koşu hızları (aralıklı antrenman reçetesi)."""
    r = _derive_or_422(perf.vift_to_aerobic_targets, payload.vift)
    return VIFTTargetsOut(**asdict(r))


class RtpClearanceIn(BaseModel):
    current: dict[str, float] = Field(..., description="Dönüş ölçümleri {protokol: değer}")
    baseline: dict[str, float] = Field(..., description="Sakatlık-öncesi {protokol: değer}")


class RtpClearanceOut(BaseModel):
    ratios: dict[str, float]
    lowest_protocol: str
    lowest_ratio: float
    cleared: bool
    light: str
    note: str


@router.post("/derive/rtp-clearance", response_model=RtpClearanceOut)
def derive_rtp_clearance(payload: RtpClearanceIn) -> RtpClearanceOut:
    """Çok-protokol return-to-play: ortak testleri baseline ile kıyasla → yeşil/kırmızı ışık."""
    r = _derive_or_422(perf.return_to_play_clearance, payload.current, payload.baseline)
    return RtpClearanceOut(**asdict(r))


class ReadinessIn(BaseModel):
    """Bir oyuncunun türetilmiş test metrikleri — hepsi opsiyonel, verilen
    değerlendirilir. Eksik metrik kararda atlanır."""
    rtp: tuple[float, float, bool] | None = Field(
        None, description="(current, baseline, higher_is_better)")
    hq: tuple[float, float] | None = Field(
        None, description="(hamstring, quadriceps) izokinetik tepe tork")
    asymmetry: tuple[float, float, str] | None = Field(
        None, description="(sol, sağ, test_adı) bacak asimetri")
    rsa: list[float] | None = Field(
        None, min_length=2, max_length=20, description="Tekrarlı sprint süreleri (sn)")
    cod: tuple[float, float] | None = Field(
        None, description="(505_süresi, 10m_düz) COD deficit")
    adductor: tuple[float, float] | None = Field(
        None, description="(güncel, önceki) adductor squeeze")
    cmj: tuple[float, list[float]] | None = Field(
        None, description="(güncel, baseline_değerleri) CMJ")
    acwr: float | None = Field(None, gt=0, description="Akut:kronik yük oranı")


class ReadinessFlagOut(BaseModel):
    metric: str
    engine: str
    severity: str
    value: str
    threshold: str
    action: str


class ReadinessOut(BaseModel):
    light: str
    verdict: str
    red_count: int
    yellow_count: int
    checked: int
    flags: list[ReadinessFlagOut]
    summary: str


@router.post("/readiness", response_model=ReadinessOut)
def assess_player_readiness(payload: ReadinessIn) -> ReadinessOut:
    """Türetilmiş test metriklerini tek hazırlık kararına sentezler.

    Verilen her metrik kendi flag motorundan geçer; en kötü severity genel
    ışığı belirler (kırmızı 'sahaya çıkmasın' > sarı 'izle/yük yönet' > yeşil
    'tam maça hazır'). Canlı maç 'En İyi Hamle' sentezinin test karşılığı."""
    r = _derive_or_422(
        perf.assess_readiness,
        rtp=payload.rtp, hq=payload.hq, asymmetry=payload.asymmetry,
        rsa=payload.rsa, cod=payload.cod, adductor=payload.adductor,
        cmj=payload.cmj, acwr=payload.acwr,
    )
    return ReadinessOut(**asdict(r))


class PositionPresetOut(BaseModel):
    position: str
    protocols: list[ProtocolInfoOut]   # önerilen protokollerin tam tanımı


@router.get("/presets/{position}", response_model=PositionPresetOut)
def get_position_preset(position: str) -> PositionPresetOut:
    """Mevkiye özel önerilen test paketi (kaleci/stoper/bek/kanat/orta_saha/forvet).

    Bilinmeyen mevki → genel batarya. Auth gerektirmez (tester tableti)."""
    keys = perf.protocols_for_position(position)
    protos: list[ProtocolInfoOut] = []
    for key in keys:
        proto = perf.PROTOCOLS.get(key)
        if proto is None:
            continue
        norms = dict(proto.norm_cutoffs)
        ref = REFERENCE.get(key)
        protos.append(ProtocolInfoOut(
            key=proto.key, name=proto.name, unit=proto.unit,
            higher_is_better=proto.higher_is_better, description=proto.description,
            norm_elite=norms["elit"], norm_good=norms["iyi"],
            norm_average=norms["ortalama"],
            ref_low=float(ref["low"]) if ref is not None else None,
            ref_high=float(ref["high"]) if ref is not None else None,
        ))
    return PositionPresetOut(position=position.strip().lower(), protocols=protos)


class BatchTestItem(BaseModel):
    player_id: str = Field(..., description="API-Football player ID")
    player_name: str = Field(..., description="Oyuncu adı")
    value: float = Field(..., description="Ölçülen değer")
    notes: str | None = Field(None)


class PhysicalTestBatchCreate(BaseModel):
    protocol: TestProtocol = Field(..., description="Tüm kayıtlar için aynı protokol")
    test_date: date = Field(..., description="Test tarihi (tüm kayıtlar için)")
    recorded_by: str | None = Field(None)
    items: list[BatchTestItem] = Field(..., min_length=1, max_length=50,
                                       description="En az 1, en fazla 50 oyuncu")


class BatchResultOut(BaseModel):
    created: int
    failed: int
    errors: list[str]          # başarısız satırlar (player_id + sebep)
    risk_alerts: list[str]     # batch sonrası kritik riske düşen oyuncular


@router.post("/batch", response_model=BatchResultOut, status_code=status.HTTP_201_CREATED)
def create_batch(
    payload: PhysicalTestBatchCreate,
    session: Session = Depends(get_session),
    user: models.User = Depends(get_current_user),
) -> BatchResultOut:
    """Bir protokol için tüm kadronun test sonuçlarını tek istekte kaydet.

    Kısmi başarı: hatalı satırlar atlanır, diğerleri kaydedilir.
    Kritik riske düşen oyuncular risk_alerts listesinde döner.
    """
    unit = UNIT_MAP.get(payload.protocol, "")
    recorded_by = payload.recorded_by or user.email

    created_players: list[tuple[str, str]] = []   # (player_id, player_name)
    errors: list[str] = []
    for item in payload.items:
        try:
            record = PhysicalTest(
                tenant_id=user.tenant_id,           # body'den gelen tenant ignore
                player_id=item.player_id,
                player_name=item.player_name,
                test_date=payload.test_date,
                protocol=payload.protocol.value,
                value=item.value,
                unit=unit,
                notes=item.notes,
                recorded_by=recorded_by,
            )
            session.add(record)
            created_players.append((item.player_id, item.player_name))
        except Exception as e:  # noqa: BLE001 — hatalı satır batch'i durdurmamalı
            errors.append(f"{item.player_id}: {e}")

    session.commit()   # tüm başarılı insert'ler tek commit

    # KVKK: her oyuncu için ayrı denetim logu (record_data_access içeride commit eder).
    for pid, _name in created_players:
        _log_access(
            session, player_id=pid, action="batch_create",
            endpoint="/physical-tests/batch", user_id=user.id,
        )

    # Kritik risk: batch sonrası her oyuncuyu değerlendir.
    risk_alerts: list[str] = []
    for pid, name in created_players:
        report = _player_risk(session, tenant_id=user.tenant_id, player_id=pid)
        if report is not None and report.risk_label == CRITICAL_LABEL:
            risk_alerts.append(f"{name} — Kritik risk")
            _maybe_alert_critical(report)

    return BatchResultOut(
        created=len(created_players),
        failed=len(errors),
        errors=errors,
        risk_alerts=risk_alerts,
    )


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


def _readiness_kwargs_from_latest(latest: dict[str, PhysicalTest]) -> dict[str, Any]:
    """Oyuncunun protokol→en son test eşlemesinden assess_readiness kwargs'ı.

    Frontend lib/readiness.ts:inputFromRecords ile birebir aynı eşleme; ham
    girdiler `components`'ten okunur (yoksa o metrik atlanır)."""
    def comp(rec: PhysicalTest, key: str) -> Any:
        return (rec.components or {}).get(key)

    def isnum(x: Any) -> bool:
        return isinstance(x, (int, float))

    kw: dict[str, Any] = {}

    ham = latest.get("isokinetic_ham")
    if ham is not None:
        quad = comp(ham, "quadriceps")
        if quad is None and "isokinetic_quad" in latest:
            quad = latest["isokinetic_quad"].value
        if isnum(quad) and quad > 0:
            kw["hq"] = (ham.value, float(quad))

    th = latest.get("triple_hop")
    if th is not None:
        left, right = comp(th, "left"), comp(th, "right")
        if isnum(left) and isnum(right):
            kw["asymmetry"] = (float(left), float(right), "Triple Hop")

    rsa = latest.get("rsa")
    if rsa is not None:
        st = comp(rsa, "sprint_times")
        if isinstance(st, list) and len(st) >= 2 and all(isnum(x) for x in st):
            kw["rsa"] = [float(x) for x in st]

    cod = latest.get("t505")
    if cod is not None:
        lin = comp(cod, "linear_10m")
        if isnum(lin) and lin > 0 and cod.value > 0:
            kw["cod"] = (cod.value, float(lin))

    add = latest.get("adductor_squeeze")
    if add is not None:
        prev = comp(add, "previous")
        if isnum(prev) and prev > 0:
            kw["adductor"] = (add.value, float(prev))

    cmj = latest.get("cmj")
    if cmj is not None:
        base = comp(cmj, "baseline_values")
        if isinstance(base, list) and base and all(isnum(x) for x in base):
            kw["cmj"] = (cmj.value, [float(x) for x in base])

    return kw


class SquadReadinessRowOut(BaseModel):
    player_id: str
    player_name: str
    decision: ReadinessOut


@router.get("/squad-readiness", response_model=list[SquadReadinessRowOut])
def squad_readiness(
    session: Session = Depends(get_session),
    user: models.User = Depends(get_current_user),
) -> list[SquadReadinessRowOut]:
    """Kadro geneli Hazırlık Kararı: her oyuncunun SON testlerinden assess_readiness.

    Demo frontend'in localStorage panosunun production karşılığı — tek istekte
    tüm kadronun 🔴/🟡/🟢 kararı (canlı maç motorlarıyla aynı saf-hesap katmanı).
    `/{player_id}` ucundan ÖNCE tanımlı (yoksa player_id sanılır)."""
    rows = list(session.execute(
        select(PhysicalTest)
        .where(PhysicalTest.tenant_id == user.tenant_id)
        .order_by(PhysicalTest.test_date.desc(), PhysicalTest.id.desc())
    ).scalars())

    # Oyuncu → {protokol: en son kayıt} (desc sıralı → ilk görülen en yenisi).
    by_player: dict[str, dict[str, PhysicalTest]] = {}
    names: dict[str, str] = {}
    for r in rows:
        names.setdefault(r.player_id, r.player_name)
        by_player.setdefault(r.player_id, {}).setdefault(r.protocol, r)

    out: list[SquadReadinessRowOut] = []
    for pid, latest in by_player.items():
        decision = perf.assess_readiness(**_readiness_kwargs_from_latest(latest))
        out.append(SquadReadinessRowOut(
            player_id=pid, player_name=names.get(pid, pid),
            decision=ReadinessOut(**asdict(decision)),
        ))
    # Kırmızı önce, sonra sarı/yeşil.
    light_rank = {"kırmızı": 0, "sarı": 1, "yeşil": 2}
    out.sort(key=lambda x: light_rank.get(x.decision.light, 9))
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


class SWCAssessmentOut(BaseModel):
    protocol_key: str
    protocol_name: str
    current: float
    baseline_mean: float
    swc: float
    delta: float
    beyond_swc: bool
    verdict: str   # "anlamlı gelişme" | "anlamlı düşüş — kontrol et" | "değişim yok …"


class BatteryOut(BaseModel):
    player_id: str
    player_name: str
    test_date: str          # en son test tarihi
    strong_areas: list[str]
    weak_areas: list[str]
    scores: list[dict]      # TestScore dataclass → dict
    swc_assessments: list[SWCAssessmentOut]   # sadece ≥3 geçmişi olan protokoller


@router.get("/{player_id}/battery", response_model=BatteryOut)
def get_battery(
    player_id: str,
    session: Session = Depends(get_session),
    user: models.User = Depends(get_current_user),
) -> BatteryOut:
    """Son test oturumundan atlet profili: güçlü/zayıf alan + SWC yorumu.

    Son test tarihindeki tüm protokolleri kullanır.
    Aynı protokolde ≥3 geçmiş kayıt varsa SWC ile anlam yorumu eklenir.
    """
    rows = list(
        session.execute(
            select(PhysicalTest)
            .where(
                PhysicalTest.tenant_id == user.tenant_id,
                PhysicalTest.player_id == player_id,
            )
            .order_by(PhysicalTest.test_date.desc())
            .limit(100)
        ).scalars()
    )
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"player_id={player_id} için test kaydı bulunamadı.",
        )

    latest_date = rows[0].test_date
    # Son test gününün protokolleri (engine'in bildiği protokollerle sınırlı).
    latest_tests = [
        t for t in rows
        if t.test_date == latest_date and t.protocol in perf.PROTOCOLS
    ]
    battery = perf.evaluate_battery(
        int(player_id) if player_id.isdigit() else 0,
        [(t.protocol, t.value) for t in latest_tests],
    )

    # SWC: protokol başına tüm geçmiş (kronolojik) ≥3 kayıt varsa anlam yorumu.
    swc_assessments: list[SWCAssessmentOut] = []
    for proto_key in {t.protocol for t in latest_tests}:
        proto = perf.PROTOCOLS[proto_key]
        history = sorted(
            (r for r in rows if r.protocol == proto_key),
            key=lambda r: r.test_date,
        )
        values = [r.value for r in history]
        if len(values) < 3:
            continue
        change = perf.assess_change(
            values[-1], values[:-1], higher_is_better=proto.higher_is_better,
        )
        swc_assessments.append(SWCAssessmentOut(
            protocol_key=proto_key,
            protocol_name=proto.name,
            current=change.current,
            baseline_mean=change.baseline_mean,
            swc=change.swc,
            delta=change.delta,
            beyond_swc=change.beyond_swc,
            verdict=change.verdict,
        ))
    swc_assessments.sort(key=lambda s: s.protocol_key)

    _log_access(
        session, player_id=player_id, action="read",
        endpoint="/physical-tests/{player_id}/battery", user_id=user.id,
    )
    return BatteryOut(
        player_id=player_id,
        player_name=rows[0].player_name,
        test_date=str(latest_date),
        strong_areas=list(battery.strong_areas),
        weak_areas=list(battery.weak_areas),
        scores=[asdict(s) for s in battery.scores],
        swc_assessments=swc_assessments,
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


@router.get("/{player_id}/pdf", responses={200: {"content": {"application/pdf": {}}}})
def get_pdf(
    player_id: str,
    session: Session = Depends(get_session),
    user: models.User = Depends(get_current_user),
) -> Response:
    """Oyuncunun kayıtlı testlerinden PDF performans raporu (norm + risk).

    Eski batarya PDF'inin (System A) B'ye taşınmış hâli: veriyi tekrar
    girmeden, DB'deki kayıtlardan üretir. KVKK: export_pdf loglanır."""
    rows = list(
        session.execute(
            select(PhysicalTest)
            .where(
                PhysicalTest.tenant_id == user.tenant_id,
                PhysicalTest.player_id == player_id,
            )
            .order_by(PhysicalTest.test_date.desc())
            .limit(50)
        ).scalars()
    )
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"player_id={player_id} için test kaydı bulunamadı.",
        )

    scores: list[dict[str, Any]] = []
    strong: list[str] = []
    weak: list[str] = []
    for r in rows:
        rating = rate_against_norms(r.protocol, r.value) or "—"
        scores.append({
            "protocol_key": r.protocol, "protocol_name": r.protocol,
            "raw_value": r.value, "unit": r.unit or "",
            "rating": rating, "squad_percentile": None,
        })
        if rating == "elit":
            strong.append(r.protocol)
        elif rating == "zayıf":
            weak.append(r.protocol)

    report = compute_load_risk(
        player_id, rows[0].player_name,
        [
            {"protocol": r.protocol, "value": r.value,
             "unit": r.unit, "test_date": r.test_date}
            for r in rows
        ],
    )
    _log_access(
        session, player_id=player_id, action="export_pdf",
        endpoint="/physical-tests/{player_id}/pdf", user_id=user.id,
    )

    from app.reports.pdf import ReportlabNotInstalled, build_performance_report_pdf
    try:
        pdf_bytes = build_performance_report_pdf(
            player_name=rows[0].player_name,
            player_external_id=int(player_id) if player_id.isdigit() else 0,
            test_date=str(rows[0].test_date),
            scores=scores,
            strong_areas=strong,
            weak_areas=weak,
            summary=f"{report.risk_label} risk — {report.summary}",
            club_name=None,
        )
    except ReportlabNotInstalled as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="performans_{player_id}.pdf"',
        },
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
