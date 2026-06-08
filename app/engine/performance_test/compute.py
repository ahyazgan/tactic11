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
    # ── Faz 2 ek protokolleri (sürat split / çeviklik / patlayıcı / MD+1). ──
    "sprint_5m": TestProtocol(
        key="sprint_5m", name="5m Sprint (reaksiyon/ilk adım)", unit="sn",
        higher_is_better=False,
        description=("Foto-hücre; durağan başlangıç, 5m. Reaksiyon + ilk adım gücü "
                     "(0-5m). 2 deneme, en iyisi. Elit ≤0.95sn, ortalama ~1.15sn."),
        norm_cutoffs=(("elit", 0.95), ("iyi", 1.05), ("ortalama", 1.15)),
    ),
    "t505": TestProtocol(
        key="t505", name="505 Çeviklik (yön değiştirme)", unit="sn",
        higher_is_better=False,
        description=("10m hızlan, çizgide 180° dön, 5m geri çık; kapı 5m'de. "
                     "Frenleme + yeniden hızlanma. COD Deficit için 10m düz sprintle "
                     "kıyaslanır. Elit ≤2.20sn, ortalama ~2.60sn."),
        norm_cutoffs=(("elit", 2.20), ("iyi", 2.40), ("ortalama", 2.60)),
    ),
    "arrowhead": TestProtocol(
        key="arrowhead", name="Arrowhead Çeviklik", unit="sn",
        higher_is_better=False,
        description=("Ok-başı koni düzeni; sağ/sol dallanan yön değiştirme. "
                     "Çok yönlü çeviklik. Elit ≤7.50sn, ortalama ~8.50sn."),
        norm_cutoffs=(("elit", 7.50), ("iyi", 8.00), ("ortalama", 8.50)),
    ),
    "illinois": TestProtocol(
        key="illinois", name="Illinois Çeviklik", unit="sn",
        higher_is_better=False,
        description=("10×5m alanda slalom + düz koşu; ivmelenme + slalom çevikliği. "
                     "Elit ≤15.20sn, ortalama ~16.80sn."),
        norm_cutoffs=(("elit", 15.20), ("iyi", 16.00), ("ortalama", 16.80)),
    ),
    "ift_30_15": TestProtocol(
        key="ift_30_15", name="30-15 IFT (VIFT — maksimal aralıklı koşu hızı)", unit="km/sa",
        higher_is_better=True,
        description=("30s koşu + 15s yürüme dinlenme, artan hız; uyamayınca biter. "
                     "Ulaşılan son kademe hızı = VIFT (aralıklı koşu reçetesinin temeli). "
                     "VO2max kestirimi için Buchheit formülü. Elit ≥21.5, ortalama ~18.5 km/sa."),
        norm_cutoffs=(("elit", 21.5), ("iyi", 20.0), ("ortalama", 18.5)),
    ),
    "adductor_squeeze": TestProtocol(
        key="adductor_squeeze", name="Adductor Squeeze (kasık kuvveti)", unit="N",
        higher_is_better=True,
        description=("Sırtüstü, dizler 45°, dinamometre dizler arasında; izometrik "
                     "iç-bacak sıkma kuvveti. MD+1 kasık/pubis takibi: baseline'a göre "
                     ">%10 düşüş riskli. Elit ≥400N, ortalama ~280N."),
        norm_cutoffs=(("elit", 400.0), ("iyi", 340.0), ("ortalama", 280.0)),
    ),
    "drop_jump_rsi": TestProtocol(
        key="drop_jump_rsi", name="Drop Jump RSI (reaktif kuvvet)", unit="RSI",
        higher_is_better=True,
        description=("30cm kutudan in, yere değer değmez maksimum sıçra; "
                     "RSI = havada kalma / yere temas süresi. Reaktif/elastik güç. "
                     "Elit ≥2.50, ortalama ~1.50."),
        norm_cutoffs=(("elit", 2.50), ("iyi", 2.00), ("ortalama", 1.50)),
    ),
    "triple_hop": TestProtocol(
        key="triple_hop", name="Triple Hop (tek bacak, 3 sıçrama mesafesi)", unit="cm",
        higher_is_better=True,
        description=("Tek bacak ardışık 3 sıçrama toplam mesafesi (sol/sağ ayrı ölçülür); "
                     "bacak asimetrisi (>%10 sarı, >%15 kırmızı) için. "
                     "Elit ≥600cm, ortalama ~480cm."),
        norm_cutoffs=(("elit", 600.0), ("iyi", 540.0), ("ortalama", 480.0)),
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


# --------------------------------------------------------------------------- #
# Türetilmiş metrikler — ham ölçümden spor-bilimi göstergesi üret (saf).
# Tüm eşikler aşağıda adlandırılmış sabit (ev konvansiyonu: engine eşiği =
# modül sabiti, env değil). DB/HTTP yok; ham sayı girer, dataclass çıkar.
# --------------------------------------------------------------------------- #

# Bangsbo (2008) Yo-Yo IR1 → VO2max: VO2 = mesafe(m) × 0.0084 + 36.4.
YOYO_IR1_VO2_SLOPE = 0.0084
YOYO_IR1_VO2_INTERCEPT = 36.4
# RSA yorgunluk indeksi: FI > %7 → yetersiz toparlanma bayrağı.
RSA_FATIGUE_FLAG_PCT = 7.0
# 505 COD Deficit: 505 − 10m düz sprint; bu eşik üstü zayıf frenleme/deceleration.
COD_DEFICIT_FLAG_S = 1.00
# Bacak (limb) asimetri eşikleri: > %10 sarı (izle), > %15 kırmızı (müdahale).
ASYMMETRY_WARN_PCT = 10.0
ASYMMETRY_HIGH_PCT = 15.0
# MD+1 Adductor Squeeze: önceki ölçüme göre > %10 düşüş → kasık/pubis riski.
ADDUCTOR_DROP_FLAG_PCT = 10.0
# MD+1 CMJ nöromusküler yorgunluk: baseline'a göre > %10 düşüş → yorgunluk.
CMJ_FATIGUE_DROP_PCT = 10.0
# Return-to-play: baseline'ın ≥ %95'i → yeşil ışık; altı → kırmızı (sahaya çıkmasın).
RTP_GREEN_LIGHT_PCT = 95.0


def derive_vo2max_from_yoyo_ir1(distance_m: float) -> float:
    """Yo-Yo IR1 toplam mesafesinden (m) VO2max kestirimi — Bangsbo (2008).

    VO2max = mesafe × 0.0084 + 36.4 (ml/kg/dk). Girdi mesafedir; seviye değil
    (seviye→mesafe dönüşümü protokol tablosundan manuel girilir)."""
    if distance_m < 0:
        raise ValueError("mesafe negatif olamaz")
    return round(distance_m * YOYO_IR1_VO2_SLOPE + YOYO_IR1_VO2_INTERCEPT, 1)


def estimate_vo2max_from_vift(
    vift_kmh: float, age: int, weight_kg: float, *, female: bool = False,
) -> float:
    """30-15 IFT son kademe hızından (VIFT) VO2max kestirimi — Buchheit (2008).

    VO2max = 28.3 − 2.15·G − 0.741·A − 0.0357·W + 0.0586·A·VIFT + 1.03·VIFT
    (G: erkek=1, kadın=2; A: yaş; W: kg). ml/kg/dk."""
    if vift_kmh <= 0:
        raise ValueError("VIFT pozitif olmalı")
    g = 2 if female else 1
    vo2 = (28.3 - 2.15 * g - 0.741 * age - 0.0357 * weight_kg
           + 0.0586 * age * vift_kmh + 1.03 * vift_kmh)
    return round(vo2, 1)


@dataclass(frozen=True)
class RSAFatigueReport:
    n: int
    best: float
    mean: float
    total: float
    fatigue_index_pct: float     # FI = ((total/(best·n)) − 1) × 100
    insufficient_recovery: bool  # FI > %7
    note: str = ""


def repeated_sprint_fatigue_index(sprint_times: list[float]) -> RSAFatigueReport:
    """Tekrarlı sprint (ör. 6×30m) sürelerinden Yorgunluk İndeksi (FI).

    FI = [(toplam_süre / (en_iyi_süre × sprint_sayısı)) − 1] × 100.
    FI > %7 → 'yetersiz toparlanma' bayrağı (anaerobik dayanıklılık zayıf)."""
    if len(sprint_times) < 2:
        raise ValueError("FI için en az 2 sprint gerekir")
    if any(t <= 0 for t in sprint_times):
        raise ValueError("sprint süreleri pozitif olmalı")
    n = len(sprint_times)
    best = min(sprint_times)
    total = sum(sprint_times)
    mean = total / n
    fi = ((total / (best * n)) - 1) * 100
    fi = round(fi, 2)
    flag = fi > RSA_FATIGUE_FLAG_PCT
    note = f"FI %{fi} ({n} sprint, en iyi {round(best, 2)}sn)"
    if flag:
        note += f" — yetersiz toparlanma (>%{RSA_FATIGUE_FLAG_PCT:g})"
    return RSAFatigueReport(
        n=n, best=round(best, 3), mean=round(mean, 3), total=round(total, 3),
        fatigue_index_pct=fi, insufficient_recovery=flag, note=note,
    )


@dataclass(frozen=True)
class CODDeficitReport:
    cod_time: float          # 505 süresi
    linear_time: float       # 10m düz sprint
    deficit: float           # cod − linear
    poor_deceleration: bool  # deficit > eşik
    note: str = ""


def change_of_direction_deficit(
    cod_time: float, linear_10m: float,
) -> CODDeficitReport:
    """COD Deficit = 505_süresi − 10m_düz_sprint. Yüksek → zayıf frenleme.

    Düz hızdan arındırılmış 'saf yön değiştirme maliyeti'; eşik üstü
    deceleration/frenleme zayıflığı (sakatlık + verim riski)."""
    if cod_time <= 0 or linear_10m <= 0:
        raise ValueError("süreler pozitif olmalı")
    deficit = round(cod_time - linear_10m, 3)
    poor = deficit > COD_DEFICIT_FLAG_S
    note = f"COD Deficit {deficit}sn"
    if poor:
        note += f" — zayıf frenleme/deceleration (>%{COD_DEFICIT_FLAG_S:g}sn)"
    return CODDeficitReport(
        cod_time=round(cod_time, 3), linear_time=round(linear_10m, 3),
        deficit=deficit, poor_deceleration=poor, note=note,
    )


def reactive_strength_index(flight_time_s: float, contact_time_s: float) -> float:
    """Drop Jump RSI = havada kalma süresi / yere temas süresi (saf).

    Reaktif/elastik kuvvet göstergesi; yüksek iyi."""
    if contact_time_s <= 0:
        raise ValueError("temas süresi pozitif olmalı")
    if flight_time_s < 0:
        raise ValueError("uçuş süresi negatif olamaz")
    return round(flight_time_s / contact_time_s, 3)


@dataclass(frozen=True)
class AsymmetryReport:
    left: float
    right: float
    asymmetry_pct: float     # |L−R| / max(L,R) × 100
    stronger_side: str       # "sol" | "sağ" | "denge"
    flag: str                # "yeşil" | "sarı" | "kırmızı"
    note: str = ""


def limb_asymmetry(left: float, right: float) -> AsymmetryReport:
    """İki bacak ölçümünden asimetri yüzdesi + bayrak (Triple Hop vb.).

    asimetri = |sol − sağ| / max(sol, sağ) × 100. > %10 sarı, > %15 kırmızı
    (sakatlık/yeniden-sakatlanma riski)."""
    if left < 0 or right < 0:
        raise ValueError("ölçümler negatif olamaz")
    hi = max(left, right)
    if hi == 0:
        raise ValueError("en az bir ölçüm pozitif olmalı")
    asym = round(abs(left - right) / hi * 100, 2)
    if abs(left - right) < 1e-9:
        side = "denge"
    else:
        side = "sol" if left > right else "sağ"
    if asym > ASYMMETRY_HIGH_PCT:
        flag = "kırmızı"
    elif asym > ASYMMETRY_WARN_PCT:
        flag = "sarı"
    else:
        flag = "yeşil"
    note = f"asimetri %{asym} ({flag}); güçlü taraf: {side}"
    return AsymmetryReport(
        left=round(left, 3), right=round(right, 3), asymmetry_pct=asym,
        stronger_side=side, flag=flag, note=note,
    )


@dataclass(frozen=True)
class DropChangeReport:
    current: float
    previous: float
    drop_pct: float          # (previous − current) / previous × 100 (pozitif = düşüş)
    flagged: bool
    note: str = ""


def adductor_squeeze_drop(current: float, previous: float) -> DropChangeReport:
    """MD+1 Adductor Squeeze: önceki ölçüme göre düşüş yüzdesi + kasık/pubis flag.

    Kuvvet düştükçe risk: düşüş > %10 → pubis/kasık riski bayrağı."""
    if previous <= 0 or current < 0:
        raise ValueError("kuvvet değerleri geçersiz")
    drop = round((previous - current) / previous * 100, 2)
    flag = drop > ADDUCTOR_DROP_FLAG_PCT
    note = f"adductor %{drop} düşüş" if drop > 0 else f"adductor %{abs(drop)} artış"
    if flag:
        note += f" — kasık/pubis riski (>%{ADDUCTOR_DROP_FLAG_PCT:g})"
    return DropChangeReport(
        current=round(current, 3), previous=round(previous, 3),
        drop_pct=drop, flagged=flag, note=note,
    )


def cmj_neuromuscular_drop(current: float, baseline_values: list[float]) -> DropChangeReport:
    """MD+1 CMJ: baseline ortalamasına göre düşüş yüzdesi + nöromusküler yorgunluk flag.

    CMJ yüksekliği baseline'ın > %10 altındaysa nöromusküler yorgunluk bayrağı
    (toparlanmamış kas-sinir sistemi → sakatlık + verim riski)."""
    if current < 0:
        raise ValueError("CMJ negatif olamaz")
    if not baseline_values:
        raise ValueError("baseline gerekli")
    baseline_mean = statistics.fmean(baseline_values)
    if baseline_mean <= 0:
        raise ValueError("baseline ortalaması pozitif olmalı")
    drop = round((baseline_mean - current) / baseline_mean * 100, 2)
    flag = drop > CMJ_FATIGUE_DROP_PCT
    note = f"CMJ baseline'a göre %{drop} düşüş" if drop > 0 else f"CMJ %{abs(drop)} üstünde"
    if flag:
        note += f" — nöromusküler yorgunluk (>%{CMJ_FATIGUE_DROP_PCT:g})"
    return DropChangeReport(
        current=round(current, 3), previous=round(baseline_mean, 3),
        drop_pct=drop, flagged=flag, note=note,
    )


@dataclass(frozen=True)
class ReturnToPlayReport:
    current: float
    baseline: float
    pct_of_baseline: float   # yön'e göre normalize (100 = baseline'a eşit)
    cleared: bool            # ≥ %95 → yeşil ışık
    light: str               # "yeşil" | "kırmızı"
    note: str = ""


def return_to_play_readiness(
    current: float, pre_injury_baseline: float, *, higher_is_better: bool = True,
) -> ReturnToPlayReport:
    """Sakatlık dönüşü: mikro-test sonucunu sakatlık-öncesi baseline ile kıyasla.

    pct = (current/baseline) [yüksek iyi] ya da (baseline/current) [düşük iyi] × 100.
    ≥ %95 → yeşil ışık (sahaya çıkabilir); < %95 → kırmızı (sahaya çıkmasın)."""
    if pre_injury_baseline <= 0 or current <= 0:
        raise ValueError("değerler pozitif olmalı")
    ratio = (current / pre_injury_baseline if higher_is_better
             else pre_injury_baseline / current)
    pct = round(ratio * 100, 1)
    cleared = pct >= RTP_GREEN_LIGHT_PCT
    light = "yeşil" if cleared else "kırmızı"
    note = (f"baseline'ın %{pct}'i — "
            + ("yeşil ışık (sahaya çıkabilir)" if cleared
               else f"kırmızı ışık (sahaya çıkmasın, hedef ≥%{RTP_GREEN_LIGHT_PCT:g})"))
    return ReturnToPlayReport(
        current=round(current, 3), baseline=round(pre_injury_baseline, 3),
        pct_of_baseline=pct, cleared=cleared, light=light, note=note,
    )


# --------------------------------------------------------------------------- #
# Hamstring:Quadriceps (H:Q) oranı — en güçlü hamstring sakatlık prediktörü.
# Konsantrik H:Q literatürde ~0.60 hedef; < 0.47 yüksek risk (kas dengesizliği).
# --------------------------------------------------------------------------- #

# Konsantrik H:Q oranı bantları (izokinetik tepe tork temelli).
HQ_RATIO_IDEAL_MIN = 0.60   # ≥ bu → ideal denge
HQ_RATIO_RISK = 0.47        # < bu → yüksek hamstring sakatlık riski


@dataclass(frozen=True)
class HQRatioReport:
    hamstring: float
    quadriceps: float
    ratio: float             # hamstring / quadriceps
    band: str                # "ideal" | "sınırda" | "yüksek_risk"
    at_risk: bool            # ratio < HQ_RATIO_RISK
    note: str = ""


def hamstring_quad_ratio(hamstring: float, quadriceps: float) -> HQRatioReport:
    """İzokinetik hamstring ve quadriceps tepe torkundan H:Q oranı + risk bandı.

    H:Q = hamstring / quadriceps (aynı açısal hız, ör. 60°/sn). Birim oranlandığı
    için Nm da Nm/kg da olur (ikisi de aynı oyuncudan). ≥0.60 ideal, 0.47-0.60
    sınırda (izle), <0.47 yüksek hamstring sakatlık riski (kuadriseps baskın)."""
    if hamstring < 0 or quadriceps <= 0:
        raise ValueError("quadriceps pozitif, hamstring negatif olamaz")
    ratio = round(hamstring / quadriceps, 3)
    if ratio >= HQ_RATIO_IDEAL_MIN:
        band = "ideal"
    elif ratio >= HQ_RATIO_RISK:
        band = "sınırda"
    else:
        band = "yüksek_risk"
    at_risk = ratio < HQ_RATIO_RISK
    note = f"H:Q {ratio} ({band})"
    if at_risk:
        note += f" — yüksek hamstring riski (hedef ≥{HQ_RATIO_IDEAL_MIN:g}, kuadriseps baskın)"
    return HQRatioReport(
        hamstring=round(hamstring, 3), quadriceps=round(quadriceps, 3),
        ratio=ratio, band=band, at_risk=at_risk, note=note,
    )


# --------------------------------------------------------------------------- #
# Mevkiye özel test paketleri — sadece preset (config) düzeyi, ayrı engine yok.
# --------------------------------------------------------------------------- #

# Mevki → o mevkide önceliklendirilen protokol seti (default batarya önerisi).
POSITION_TEST_PRESETS: dict[str, tuple[str, ...]] = {
    "kaleci": ("cmj", "sj", "drop_jump_rsi", "sprint_5m", "t505", "adductor_squeeze"),
    "stoper": ("cmj", "sprint_10m", "t505", "yoyo_irl1", "isokinetic_ham",
               "adductor_squeeze"),
    "bek": ("sprint_10m", "sprint_30m", "ift_30_15", "illinois", "rsa", "triple_hop"),
    "kanat": ("sprint_10m", "sprint_30m", "ift_30_15", "arrowhead", "rsa",
              "triple_hop"),
    "orta_saha": ("yoyo_irl1", "ift_30_15", "vo2max", "sprint_30m", "ttest_agility",
                  "cmj"),
    "forvet": ("sprint_5m", "sprint_10m", "cmj", "drop_jump_rsi", "t505",
               "adductor_squeeze"),
}
# Mevki eşleşmezse uygulanan genel batarya.
DEFAULT_POSITION_PRESET: tuple[str, ...] = (
    "sprint_10m", "sprint_30m", "yoyo_irl1", "cmj", "ttest_agility", "rsa",
)


def protocols_for_position(position: str) -> tuple[str, ...]:
    """Mevki adından (TR, büyük/küçük harf duyarsız) önerilen protokol seti.

    Bilinmeyen/boş mevki → DEFAULT_POSITION_PRESET."""
    return POSITION_TEST_PRESETS.get(position.strip().lower(), DEFAULT_POSITION_PRESET)
