"""Performance Test — spor bilimi performans testi modülü (saf).

Teknik ekibin fiziksel test ihtiyacı: protokol oku → test uygula → skorla →
yorumla. Bu engine o işin saf-hesap çekirdeği:
- Protokol kütüphanesi (YoYo IR1, 30m sprint, CMJ sıçrama, T-test çeviklik, RSA)
  her biri: birim + yön (yüksek/düşük iyi) + norm bantları + nasıl-yapılır.
- `score_test`: ham değer → norm-rating + (kadro verilirse) yüzdelik.
- `evaluate_battery`: bir test gününün tüm sonuçları → atlet profili.
- `interpret_progression`: tarihsel seri → gelişiyor/geriliyor (development_curve)
  + regresyon/sakatlık erken-uyarısı (anomaly).

Saf: DB/HTTP yok. Mevcut development_curve + anomaly motorlarını kullanır.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from app.engine.anomaly import detect_anomalies
from app.engine.development_curve import development_curve

ENGINE_NAME = "engine.performance_test"
ENGINE_VERSION = "1"

WEAK_LABEL = "zayıf"
# Gelişim yön bandı: |slope| bunun altıysa "sabit".
PROGRESS_EPS = 0.02
# SWC (Smallest Worthwhile Change): Cohen küçük etki = 0.2 × grup SD.
SWC_FACTOR = 0.2


@dataclass(frozen=True)
class TestProtocol:
    key: str
    name: str
    unit: str
    higher_is_better: bool
    description: str          # nasıl yapılır (tester'a rehber)
    # (rating, cutoff) en iyi→ortalama. higher: raw>=cutoff; lower: raw<=cutoff.
    # Hiçbiri tutmazsa WEAK_LABEL.
    norm_cutoffs: tuple[tuple[str, float], ...]


# Elit/pro futbol için yaklaşık norm eşikleri (kalibrasyon kulüp verisiyle güncellenir).
PROTOCOLS: dict[str, TestProtocol] = {
    "cmj": TestProtocol(
        key="cmj", name="Countermovement Jump (dikey sıçrama)", unit="cm",
        higher_is_better=True,
        description=("Eller belde, hızlı çömel-zıpla; force plate ya da jump mat "
                     "ile sıçrama yüksekliği. 3 deneme, en iyisi."),
        norm_cutoffs=(("elit", 40.0), ("iyi", 35.0), ("ortalama", 30.0)),
    ),
    "sprint_30m": TestProtocol(
        key="sprint_30m", name="30m Sprint", unit="sn",
        higher_is_better=False,
        description=("Foto-hücre kapıları; durağan başlangıç, 30m. 2 deneme, en iyisi. "
                     "10m split de kaydedilebilir."),
        norm_cutoffs=(("elit", 4.00), ("iyi", 4.20), ("ortalama", 4.40)),
    ),
    "yoyo_irl1": TestProtocol(
        key="yoyo_irl1", name="Yo-Yo Intermittent Recovery L1", unit="seviye",
        higher_is_better=True,
        description=("20m mekik + 10s aktif dinlenme, artan hız; bip'e uyamayınca "
                     "biter. Ulaşılan kademe/seviye (ör. 18.5)."),
        norm_cutoffs=(("elit", 20.0), ("iyi", 18.0), ("ortalama", 16.0)),
    ),
    "ttest_agility": TestProtocol(
        key="ttest_agility", name="T-Test Çeviklik", unit="sn",
        higher_is_better=False,
        description=("T şeklinde koni düzeni: ileri-yan-yan-geri. Yön değiştirme hızı."),
        norm_cutoffs=(("elit", 9.5), ("iyi", 10.5), ("ortalama", 11.5)),
    ),
    "rsa": TestProtocol(
        key="rsa", name="Tekrarlı Sprint (RSA) — ortalama", unit="sn",
        higher_is_better=False,
        description=("6×30m sprint, 20s dinlenme; sprint sürelerinin ortalaması "
                     "(yorgunluk indeksi ayrıca hesaplanır)."),
        norm_cutoffs=(("elit", 4.30), ("iyi", 4.55), ("ortalama", 4.80)),
    ),
    # ── load_risk.REFERENCE ile aynı key'ler; norm: elit=high, iyi=mid, ortalama=low.
    "sprint_10m": TestProtocol(
        key="sprint_10m", name="10m Sprint (ivmelenme)", unit="sn",
        higher_is_better=False,
        description=("Foto-hücre kapıları; durağan başlangıç, 10m. İlk adım gücü/ivmelenme. "
                     "2 deneme, en iyisi. Elit ≤1.70sn, ortalama ~1.90sn."),
        norm_cutoffs=(("elit", 1.70), ("iyi", 1.80), ("ortalama", 1.90)),
    ),
    "yoyo_irl2": TestProtocol(
        key="yoyo_irl2", name="Yo-Yo Intermittent Recovery L2", unit="seviye",
        higher_is_better=True,
        description=("L1'den daha yüksek başlangıç hızı; daha kısa sürede yüksek yoğunluk "
                     "dayanıklılığı. Ulaşılan kademe. Elit ≥18.0, ortalama ~15.0."),
        norm_cutoffs=(("elit", 18.0), ("iyi", 16.5), ("ortalama", 15.0)),
    ),
    "sj": TestProtocol(
        key="sj", name="Squat Jump (statik sıçrama)", unit="cm",
        higher_is_better=True,
        description=("90° çömelmeden, ön-gerilim olmadan dikey sıçra (eller belde). "
                     "Konsentrik güç. CMJ ile farkı elastik enerji göstergesi. "
                     "Elit ≥38cm, ortalama ~28cm."),
        norm_cutoffs=(("elit", 38.0), ("iyi", 33.0), ("ortalama", 28.0)),
    ),
    "isokinetic_quad": TestProtocol(
        key="isokinetic_quad", name="İzokinetik Quadriceps (60°/s)", unit="Nm/kg",
        higher_is_better=True,
        description=("İzokinetik dinamometre, 60°/sn; kuadriseps tepe torku / vücut ağırlığı. "
                     "Diz ekstansiyon gücü + H/Q oranı için. Elit ≥3.20, ortalama ~2.50."),
        norm_cutoffs=(("elit", 3.20), ("iyi", 2.85), ("ortalama", 2.50)),
    ),
    "isokinetic_ham": TestProtocol(
        key="isokinetic_ham", name="İzokinetik Hamstring (60°/s)", unit="Nm/kg",
        higher_is_better=True,
        description=("İzokinetik dinamometre, 60°/sn; hamstring tepe torku / vücut ağırlığı. "
                     "H/Q oranı sakatlık riskinin anahtarı. Elit ≥2.00, ortalama ~1.50."),
        norm_cutoffs=(("elit", 2.00), ("iyi", 1.75), ("ortalama", 1.50)),
    ),
    "vo2max": TestProtocol(
        key="vo2max", name="VO2max (maksimal oksijen)", unit="ml/kg/min",
        higher_is_better=True,
        description=("Doğrudan (metabolik araba) ya da Beep/Cooper'dan kestirim. "
                     "Aerobik kapasite. Elit ≥62, ortalama ~52 ml/kg/dk."),
        norm_cutoffs=(("elit", 62.0), ("iyi", 57.0), ("ortalama", 52.0)),
    ),
    "gps_total_dist": TestProtocol(
        key="gps_total_dist", name="GPS Toplam Mesafe (maç)", unit="m",
        higher_is_better=True,
        description=("GPS/LPS biriminden bir maç/antrenmandaki toplam kat edilen mesafe. "
                     "İş hacmi göstergesi. Elit ~11500m, ortalama ~9000m."),
        norm_cutoffs=(("elit", 11500.0), ("iyi", 10250.0), ("ortalama", 9000.0)),
    ),
    "gps_hir_dist": TestProtocol(
        key="gps_hir_dist", name="GPS Yüksek Şiddet Mesafe", unit="m",
        higher_is_better=True,
        description=("Yüksek-hız eşiği (>19.8 km/s) üstünde kat edilen mesafe. "
                     "Yüksek-yoğunluk iş kapasitesi. Elit ~1200m, ortalama ~800m."),
        norm_cutoffs=(("elit", 1200.0), ("iyi", 1000.0), ("ortalama", 800.0)),
    ),
    "gps_acc_count": TestProtocol(
        key="gps_acc_count", name="GPS İvmelenme Sayısı", unit="adet",
        higher_is_better=True,
        description=("Yüksek-eşik (>3 m/s²) ivmelenme/yavaşlama olay sayısı. "
                     "Nöromüsküler yük göstergesi. Elit ~50, ortalama ~30 adet."),
        norm_cutoffs=(("elit", 50.0), ("iyi", 40.0), ("ortalama", 30.0)),
    ),
    "body_fat_pct": TestProtocol(
        key="body_fat_pct", name="Vücut Yağ Oranı", unit="%",
        higher_is_better=False,
        description=("Skinfold (kaliper) ya da biyoimpedans; vücut yağ yüzdesi. "
                     "Düşük iyi (atletik kompozisyon). Elit ≤8%, ortalama ~14%."),
        norm_cutoffs=(("elit", 8.0), ("iyi", 11.0), ("ortalama", 14.0)),
    ),
}


@dataclass(frozen=True)
class TestScore:
    protocol_key: str
    protocol_name: str
    raw_value: float
    unit: str
    rating: str                  # elit/iyi/ortalama/zayıf
    higher_is_better: bool
    squad_percentile: float | None = None   # kadro içinde 0..100 (verildiyse)
    note: str = ""


def rate_against_norms(protocol: TestProtocol, raw_value: float) -> str:
    for label, cutoff in protocol.norm_cutoffs:
        if protocol.higher_is_better and raw_value >= cutoff:
            return label
        if not protocol.higher_is_better and raw_value <= cutoff:
            return label
    return WEAK_LABEL


def squad_percentile(
    raw_value: float, reference_values: list[float], *, higher_is_better: bool,
) -> float | None:
    """Kadro/grup içinde yüzdelik (100 = en iyi). Yön'e duyarlı."""
    if not reference_values:
        return None
    if higher_is_better:
        worse = sum(1 for r in reference_values if r < raw_value)
    else:
        worse = sum(1 for r in reference_values if r > raw_value)
    return round(100.0 * worse / len(reference_values), 1)


def score_test(
    protocol_key: str,
    raw_value: float,
    *,
    reference_values: list[float] | None = None,
) -> TestScore:
    """Tek bir test sonucunu norm + (varsa) kadro yüzdeliğiyle skorla."""
    protocol = PROTOCOLS.get(protocol_key)
    if protocol is None:
        raise ValueError(f"bilinmeyen protokol: {protocol_key}")
    rating = rate_against_norms(protocol, raw_value)
    pct = (squad_percentile(raw_value, reference_values,
                            higher_is_better=protocol.higher_is_better)
           if reference_values else None)
    note = f"{protocol.name}: {raw_value}{protocol.unit} → {rating}"
    if pct is not None:
        note += f" (kadro %{pct})"
    return TestScore(
        protocol_key=protocol.key, protocol_name=protocol.name,
        raw_value=raw_value, unit=protocol.unit, rating=rating,
        higher_is_better=protocol.higher_is_better,
        squad_percentile=pct, note=note,
    )


@dataclass(frozen=True)
class BatteryReport:
    player_external_id: int
    scores: tuple[TestScore, ...] = field(default_factory=tuple)
    weak_areas: tuple[str, ...] = field(default_factory=tuple)   # zayıf protokoller
    strong_areas: tuple[str, ...] = field(default_factory=tuple)  # elit protokoller


def evaluate_battery(
    player_external_id: int,
    results: list[tuple[str, float]],
    *,
    squad_references: dict[str, list[float]] | None = None,
) -> BatteryReport:
    """Bir test gününün tüm sonuçları → atlet profili (güçlü/zayıf alanlar)."""
    refs = squad_references or {}
    scores = [
        score_test(key, raw, reference_values=refs.get(key))
        for key, raw in results
    ]
    weak = tuple(s.protocol_name for s in scores if s.rating == WEAK_LABEL)
    strong = tuple(s.protocol_name for s in scores if s.rating == "elit")
    return BatteryReport(
        player_external_id=player_external_id, scores=tuple(scores),
        weak_areas=weak, strong_areas=strong,
    )


@dataclass(frozen=True)
class ProgressionReport:
    protocol_key: str
    n: int
    trend: str                   # "gelişiyor" | "geriliyor" | "sabit"
    slope: float
    projection_next: float
    regression_alert: bool       # ani düşüş (sakatlık/aşırı yük erken-uyarı)
    note: str = ""


def interpret_progression(
    protocol_key: str, values: list[float],
) -> ProgressionReport:
    """Bir protokolün tarihsel serisi → gelişiyor mu + regresyon uyarısı.

    development_curve (eğim) + anomaly (form kırılması) motorlarını kullanır;
    yön (higher_is_better) dikkate alınarak 'gelişiyor/geriliyor'a çevrilir.
    """
    protocol = PROTOCOLS.get(protocol_key)
    if protocol is None:
        raise ValueError(f"bilinmeyen protokol: {protocol_key}")
    curve = development_curve(values)
    hib = protocol.higher_is_better

    # Ham eğim "değer artıyor mu"; gelişme yön'e bağlı.
    if abs(curve.slope) <= PROGRESS_EPS:
        trend = "sabit"
    elif (curve.slope > 0) == hib:
        trend = "gelişiyor"
    else:
        trend = "geriliyor"

    # Regresyon: iyi-yönün tersine ani kırılma.
    anom = detect_anomalies(values)
    regression = bool(
        anom.break_detected
        and anom.break_direction is not None
        and ((anom.break_direction == "düşüş") == hib)
    )

    note = f"{protocol.name}: {trend}"
    if regression:
        note += " — DİKKAT: ani düşüş (sakatlık/aşırı yük kontrolü)"
    return ProgressionReport(
        protocol_key=protocol.key, n=curve.n, trend=trend,
        slope=curve.slope, projection_next=curve.projection_next,
        regression_alert=regression, note=note,
    )


# --------------------------------------------------------------------------- #
# SWC + bireysel baseline — ölçüm gürültüsünden GERÇEK değişimi ayır.
# Lig ortalaması değil, oyuncunun KENDİ geçmişine göre (asıl bilimsel değer).
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ChangeAssessment:
    current: float
    baseline_mean: float
    swc: float                   # smallest worthwhile change (0.2 × baseline SD)
    delta: float                 # current - baseline_mean
    beyond_swc: bool
    verdict: str                 # anlamlı gelişme | anlamlı düşüş | değişim yok


def smallest_worthwhile_change(
    baseline_values: list[float], *, factor: float = SWC_FACTOR,
) -> float:
    """SWC = factor × bireyin baseline standart sapması (Cohen küçük etki)."""
    if len(baseline_values) < 2:
        return 0.0
    return round(factor * statistics.pstdev(baseline_values), 3)


def assess_change(
    current: float,
    baseline_values: list[float],
    *,
    higher_is_better: bool,
    factor: float = SWC_FACTOR,
) -> ChangeAssessment:
    """Yeni ölçüm, bireyin baseline'ına göre ANLAMLI mı yoksa gürültü mü?

    |değişim| < SWC ise 'değişim yok' (ölçüm gürültüsü); aksi halde yön'e göre
    anlamlı gelişme/düşüş. Bireysel referans → lig normundan daha hassas.
    """
    baseline_mean = statistics.fmean(baseline_values) if baseline_values else current
    swc = smallest_worthwhile_change(baseline_values, factor=factor)
    delta = round(current - baseline_mean, 3)
    beyond = bool(swc > 0 and abs(delta) >= swc)
    if not beyond:
        verdict = "değişim yok (SWC altı — ölçüm gürültüsü olabilir)"
    elif (delta > 0) == higher_is_better:
        verdict = "anlamlı gelişme"
    else:
        verdict = "anlamlı düşüş — kontrol et"
    return ChangeAssessment(
        current=current, baseline_mean=round(baseline_mean, 3), swc=swc,
        delta=delta, beyond_swc=beyond, verdict=verdict,
    )
