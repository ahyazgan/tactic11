"""Koç zekâ karnesi — motorun "antrenör aklı" ne kadar ölçülebilir?

## Neden bu motor var

Külliyat (502 ölçülmüş karar, gerçek maçlar) tek bir şeyi tartıyordu: motorun
GÜVENİ sonucu ayırt ediyor mu? Cevap hayır çıktı ve sebebi de bulundu —
kararlar uygulanmadığı için "sonra ne oldu" ile "öneri yüzünden ne oldu"
ayrılamıyor. Ama "ne kadar zekâlı" sorusunun bundan başka, BUGÜN ölçülebilir
boyutları var. Bu motor onları tek karnede toplar ve her birini bir taban
çizgisiyle kıyaslar. Taban çizgisi yoksa "zekâ" sayısı anlamsızdır: 60-75.
dakikada "değişiklik yap" diyen bir sayaç da elit antrenörle sık sık uyuşur.

## Boyutlar

1. **Öngörü** — güven skoru, karar sonrası 15 dk'nın yönünü öngörüyor mu?
   Ölçü: karar öncesi duruma göre KATMANLI AUC (ortalamaya dönüş kontrolü).
   Taban: 0.5 (yazı-tura).
2. **Kalibrasyon** — sistem "%X güveniyorum" dediğinde %X tutuyor mu?
   Ölçü: beklenen kalibrasyon hatası (ECE). Taban: hiç öğrenmemiş bir sistemin
   sabit taban oranı söylemesi (ECE = |ort. güven − isabet|).
   Yalnız KALİBRE olasılıkta ölçülür: kalibrasyon kurulmamışsa saklanan sayı
   ham kanıt gücüdür, olasılık değil (panel de yüzde göstermez). Ham skoru
   0.5'e doğru "küçültüp" ECE'yi düşürmek değerlendirildi ve REDDEDİLDİ: koça
   gösterilen hiçbir şeyi değiştirmez, yalnız ölçüyü süsler. Külliyat
   uygulanmamış öneriden oluştuğu için (applied=None) bu boyut orada "ölçülemez"
   çıkar; ölçülebilmesi için koçun uyguladığı ve sonucu işaretlenmiş kararlar gerekir.
3. **Elit antrenörle uyum** — gerçek antrenör (StatsBomb) oyuncu değiştirdiği
   pencerede motor da "değişiklik" demiş miydi? Ölçü: F1. Taban: yalnız
   dakikaya bakan kural ("t ≥ T ise değiştir"), eşiği AYRIK yarıda seçilir.
   Aynı yarıda seçilip aynı yarıda ölçülen eşik hile olurdu.
4. **Cetvel kontrolü** — bizim etki cetveli, ELİT antrenörün gerçek hamlelerini
   de "olumlu" görüyor mu? Görmüyorsa cetvel kimseyi ayıramaz; motorun düşük
   puanı cetvelin körlüğüdür, motorun değil. (Script hesaplar, burada rapor.)
5. **Karşı-olgu** — uygulanan vs uygulanmayan (`decision_uplift`). Pilot
   verisi gelmeden "ölçülemez"; sayı uydurulmaz.

## Ölçüm günlüğü (2026-09-12) — derinleşme bulguları

- **Kim çıkar** (mevki grubu × ilk 11): Barcelona ayrık yarı isabet@3 %56; iki
  takım (671 değişiklik) %47. Ek özellikler denendi (ayrık yarı, iki takım):
  sarı kart, son 15 dk düşük katılım, skor durumu → sıfır ya da eksi; ≥60 dk
  oynamış +2; dakika bandı +4 (%52, @1 %19). Tavan bu civarda: antrenörün
  seçiminin yarısı olay verisinde olmayan bilgiye (GPS yorgunluk, sakatlık,
  plan) dayanıyor. +4 puan n=671'de ~1.6σ — motora bağlanmadı.
- **Diziliş değişimi** (StatsBomb Tactical Shift, 224 olay/100 maç, iki takım):
  %74'ü bir değişiklikten ±2 dk içinde geliyor (kadro değişince diziliş yeniden
  etiketleniyor); en sık geçiş 433→433 (mevki takası). 12 dk pencerede taban
  oranı %15; durum önseli F1 0.27, saat 0.32, hep-evet 0.26 — hiçbir şey
  öngörmüyor. Motorun "şekil ayarla" teması ise taktik/momentum/uzamsal/eşleşme
  sinyallerinin ortak çatısı (birincil kararların %75'i, büyüklük medyanı 1.0 —
  doygun). İkisi aynı şey DEĞİL: karnedeki diziliş satırı zayıf bir vekildir,
  motor bu satıra göre ayarlanmadı.
- **Zamanlama**: elit pencere önseli motoru saatle eşitledi (F1 0.69 / 0.74);
  saat, iki takımdan 3200 tikte önselin de tavanıydı.

## Ölçüm günlüğü (2026-09-14) — şekil seçiciliği

Bu bölüm e0237df ölçümünün tarihsel kaydıdır. Bütçe/oyuncu sayımı düzeltmeleri
sonrası aynı girdide kaldırma 1.427/1.603 oldu; aşağıdaki eski sayılar güncel
algoritmanın başarısı olarak kullanılmamalı. docs/KARNE-DUZELTME-SONUCLARI.md.

- **F1 bu soruda cetvel değil**: diziliş hedefi nadir (taban %21), hep-evet
  F1 0.35 çıkıyor — motorun 0.33'ünden yüksek. "Daha seçici ol" ile "F1'i
  yükselt" zıt yönler. Seçicilik cetveli kaldırma (precision / taban oranı)
  ve yanında bayrak oranı: `selectivity`.
- **Ham bayrak bilgi taşımıyor**: `adjust_shape` tiklerinde diziliş oranı
  0.211, genel taban 0.212 → kaldırma 0.91/1.08. Motorun sakladığı hiçbir
  sürekli sayı ayırmıyor (AUC 0.49–0.57); ayıran tek şey zaman (0.63).
- **Kapı işe yarıyor**: elit diziliş önseli (dakika × skor × değişiklik) ∧
  ≥2 destekleyici sinyal → bayrak %74'ten %19'a, kaldırma 1.65/1.85, iki
  yarıda da. Permütasyon (400 deneme, kapı sıfırdan kurularak) p 0.005/0.000.
  Bedeli: yakalama 0.74 → 0.35. Yalnız önselle 1.45/1.63; destek eşiğinin
  payı bağımsız kanıtlanmadı.
- Hedef ZAYIF VEKİL kalmaya devam ediyor (diziliş olaylarının %89'u aynı
  pencerede bir değişiklikle). Kapı ölçüm katmanındadır; motorun canlı
  çıktısı bu ölçümle kısılmadı — bkz. docs/KARNE-SEKIL-SECICILIGI.md.

Saf fonksiyonlar; DB/IO yok. Sayısal eşikler sabit ve dokümante — bir sonraki
ölçüm aynı cetvelle yapılsın diye.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

from app.engine.confidence.attribution import MIN_SAMPLES

ENGINE_NAME = "engine.coach_benchmark"
ENGINE_VERSION = "1"

# F1 farkı bu puanın altındaysa "taban çizgisiyle aynı" — gürültü bandı.
MIN_F1_GAIN = 0.05
# Her ayrık yarıda en az bu kadar tik yoksa uyum hükmü verilmez.
MIN_TICKS_PER_HALF = MIN_SAMPLES
# Dakika-kuralı adayları: klasik değişiklik pencereleri. Eşik ayrık yarıda seçilir.
DEFAULT_MINUTE_THRESHOLDS: tuple[float, ...] = (28.0, 40.0, 55.0, 66.0, 78.0)
DEFAULT_ECE_BINS = 4
# Elit zamanlama önseli: dakika bantları (üst sınır dahil değil) ve Laplace düzeltmesi.
PRIOR_MINUTE_BANDS: tuple[float, ...] = (45.0, 60.0, 70.0, 80.0)
PRIOR_MAX_SUBS = 3          # 3+ değişiklik tek hücrede toplanır (seyrek)
PRIOR_LAPLACE = 1.0
PRIOR_THRESHOLDS: tuple[float, ...] = (0.3, 0.4, 0.5, 0.6)
# "Kim" boyutu: motorun aday listesi bu uzunlukta değerlendirilir; kazanç eşiği.
WHO_TOP_K = 3
WHO_MIN_GAIN = 0.10
# Şekil seçiciliği: önsel eşik adayları, destekleyici sinyal sayısı eşikleri,
# eğitimde harcanabilecek en küçük bayrak bütçesi ve kabul için gereken kaldırma.
SHAPE_PRIOR_THRESHOLDS: tuple[float, ...] = (0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.5, 0.6)
SHAPE_SUPPORT_THRESHOLDS: tuple[int, ...] = (1, 2, 3, 4, 5)
SHAPE_MIN_FLAG_RATE = 0.15
SHAPE_MIN_LIFT = 1.25


@dataclass(frozen=True)
class TickObservation:
    """Motorun konuştuğu bir an: bu tikte 'değişiklik' dedi mi, antrenör yaptı mı?"""

    match_external_id: int
    minute: float
    engine_flag: bool     # motor bu tikte hedef türde hamle önerdi
    coach_acted: bool     # gerçek antrenör (minute, minute+window] içinde o hamleyi yaptı


@dataclass(frozen=True)
class TickState:
    """Motorun konuştuğu anın DURUMU — elit zamanlama önseli bunlardan öğrenir.

    Yalnız o ana kadar bilinen şeyler: dakika, o anki skor durumu, o ana kadar
    yapılan değişiklik sayısı. Maç sonucu buraya GİRMEZ (sızıntı olurdu).
    """

    match_external_id: int
    minute: float
    score_state: str      # "leading" | "drawing" | "trailing" (o an itibarıyla)
    subs_used: int        # takımın o ana kadar yaptığı değişiklik (sakatlık dahil)
    coach_acted: bool


@dataclass(frozen=True)
class TimingPrior:
    """Hücre → P(antrenör bu pencerede değiştirir). Ayrık yarıda öğrenilir."""

    table: dict[tuple[int, str, int], float]
    threshold: float
    fitted_on: int


@dataclass(frozen=True)
class AgreementStat:
    n: int
    tp: int
    fp: int
    fn: int
    tn: int
    precision: float | None   # bayrak kaldırdığında antrenör de yaptı mı
    recall: float | None      # antrenör yaptığında motor önceden dedi mi
    f1: float | None
    flag_rate: float          # motorun bayrak oranı — doygunluk göstergesi
    act_rate: float           # antrenörün hamle taban oranı


@dataclass(frozen=True)
class SplitHalfAgreement:
    """Motor F1 vs dakika-kuralı F1 — eşik ÖTEKİ yarıda seçilmiş."""

    engine_a: AgreementStat
    engine_b: AgreementStat
    baseline_a: AgreementStat
    baseline_b: AgreementStat
    threshold_for_a: float | None   # B'de seçildi, A'da ölçüldü
    threshold_for_b: float | None
    engine_f1: float | None         # iki yarının ortalaması
    baseline_f1: float | None
    verdict: str                    # "taban çizgisini geçiyor" | "aynı" | "altında" | "yetersiz veri"
    note: str


@dataclass(frozen=True)
class LeadTimeStat:
    """Antrenör hamlesinden ÖNCE motor kaç dakika erken dedi?"""

    moves: int
    covered: int                  # öncesinde (lookback içinde) motor bayrağı olan hamle
    coverage: float | None
    mean_lead_min: float | None   # yalnız kapsananlarda
    median_lead_min: float | None


@dataclass(frozen=True)
class WhoSample:
    """Gerçek bir değişiklik: antrenör KİMİ çıkardı, motor kimleri önermişti?"""

    player_off: int
    candidates: tuple[int, ...]   # motorun sıralı aday listesi (hamleden önceki son tik)
    on_pitch: tuple[int, ...]     # hamle anında sahadaki kendi oyuncuları


@dataclass(frozen=True)
class WhoCandidate:
    """Hamle anında sahadaki bir oyuncu — elit "kim çıkar" önseli bunlardan öğrenir."""

    player_id: int
    group: str          # "GK" | "DEF" | "MID" | "FWD" | "UNK"
    starter: bool       # ilk 11'den mi (değişiklikle girenler nadiren çıkar)


@dataclass(frozen=True)
class WhoState:
    match_external_id: int
    player_off: int
    candidates: tuple[WhoCandidate, ...]


@dataclass(frozen=True)
class WhoPrior:
    """(mevki grubu, ilk 11 mi) → P(çıkar). Ayrık yarıda öğrenilir."""

    table: dict[tuple[str, bool], float]
    fitted_on: int


@dataclass(frozen=True)
class WhoStat:
    n: int
    hit_at_1: float | None
    hit_at_k: float | None
    baseline_at_1: float | None   # rastgele sahadaki oyuncu: 1/n_saha ortalaması
    baseline_at_k: float | None   # k/n_saha ortalaması
    off_pitch_candidate_rate: float | None   # aday listesinde sahada olmayan oyuncu payı
    verdict: str
    note: str


@dataclass(frozen=True)
class ShapeState:
    """Motorun "şekil ayarla" dediği bir an ve o anın DURUMU.

    `engine_flag` motorun ham bayrağı (tema), `support_count` o tikte kaç
    destekleyici sinyalin yandığı; ikisi de kapının girdisidir. Hedef, gerçek
    antrenörün penceredeki diziliş değişimi.
    """

    match_external_id: int
    minute: float
    score_state: str        # "leading" | "drawing" | "trailing" (o an itibarıyla)
    subs_used: int          # takımın o ana kadar yaptığı değişiklik
    engine_flag: bool       # motorun ham "şekil ayarla" bayrağı
    support_count: int      # o tikteki destekleyici sinyal sayısı
    coach_acted: bool       # antrenör (minute, minute+window] içinde dizilişi değiştirdi


@dataclass(frozen=True)
class ShapePrior:
    """Hücre oranı + eşikler; uygun aday yoksa iki eşik de None olur."""

    table: dict[tuple[int, str, int], float]
    threshold: float | None
    support_threshold: int | None
    fitted_on: int


@dataclass(frozen=True)
class SelectivityStat:
    """Seçicilik cetveli: kaç bayrak, ne kadar isabet, tabanın kaç katı.

    `lift` = precision / taban oranı. 1.0 = bayrak hiçbir şey bilmiyor.
    """

    n: int
    flagged: int
    flag_rate: float
    base_rate: float
    precision: float | None
    recall: float | None
    f1: float | None
    lift: float | None


@dataclass(frozen=True)
class ShapeGate:
    """Ham bayrak vs kapılı bayrak — kapı ÖTEKİ yarıda öğrenilmiş."""

    raw_a: SelectivityStat
    raw_b: SelectivityStat
    gated_a: SelectivityStat
    gated_b: SelectivityStat
    prior_for_a: ShapePrior
    prior_for_b: ShapePrior
    verdict: str            # "seçici" | "kararsız" | "seçici değil" | "yetersiz veri"
    note: str


@dataclass(frozen=True)
class Dimension:
    name: str
    metric: str
    value: float | None
    baseline: float | None
    skill: float | None       # 0..100, taban = 0; None = bu boyutta doğal ölçek yok/ölçülemedi
    measurable: bool
    verdict: str
    note: str


@dataclass(frozen=True)
class Scorecard:
    dimensions: tuple[Dimension, ...]
    measurable: int
    beating_baseline: int
    headline: str


# --------------------------------------------------------------------------- #
# Uyum (gerçek antrenörle)
# --------------------------------------------------------------------------- #

def _safe_div(a: float, b: float) -> float | None:
    return a / b if b else None


def agreement(obs: Iterable[TickObservation]) -> AgreementStat:
    """Bayrak × hamle karışıklık matrisi → precision / recall / F1."""
    rows = list(obs)
    tp = sum(1 for o in rows if o.engine_flag and o.coach_acted)
    fp = sum(1 for o in rows if o.engine_flag and not o.coach_acted)
    fn = sum(1 for o in rows if not o.engine_flag and o.coach_acted)
    tn = len(rows) - tp - fp - fn
    p = _safe_div(tp, tp + fp)
    r = _safe_div(tp, tp + fn)
    f1 = _safe_div(2 * p * r, p + r) if p is not None and r is not None else None
    return AgreementStat(
        n=len(rows), tp=tp, fp=fp, fn=fn, tn=tn,
        precision=None if p is None else round(p, 3),
        recall=None if r is None else round(r, 3),
        f1=None if f1 is None else round(f1, 3),
        flag_rate=round(_safe_div(tp + fp, len(rows)) or 0.0, 3),
        act_rate=round(_safe_div(tp + fn, len(rows)) or 0.0, 3),
    )


def minute_rule(obs: Iterable[TickObservation], threshold: float) -> AgreementStat:
    """Taban çizgisi: motora bakmadan 'dakika ≥ eşik ise değiştir' de."""
    return agreement(
        TickObservation(o.match_external_id, o.minute, o.minute >= threshold, o.coach_acted)
        for o in obs
    )


def _best_threshold(
    obs: Sequence[TickObservation], candidates: Sequence[float],
) -> float | None:
    best: tuple[float, float] | None = None
    for t in candidates:
        f1 = minute_rule(obs, t).f1
        if f1 is None:
            continue
        if best is None or f1 > best[1]:
            best = (t, f1)
    return None if best is None else best[0]


def _halves(obs: Sequence[TickObservation]) -> tuple[list[TickObservation], list[TickObservation]]:
    """Maç bazında ayrık iki yarı (sıralı maç kimliğinin tek/çift indeksi).

    Tik bazında bölmek aynı maçın tiklerini iki yarıya dağıtır ve yarılar
    birbirinden bağımsız olmaz; kimlik sırası deterministiktir.
    """
    ids = sorted({o.match_external_id for o in obs})
    a_ids = {m for i, m in enumerate(ids) if i % 2 == 0}
    a = [o for o in obs if o.match_external_id in a_ids]
    b = [o for o in obs if o.match_external_id not in a_ids]
    return a, b


def split_half_agreement(
    obs: Sequence[TickObservation], *,
    candidates: Sequence[float] = DEFAULT_MINUTE_THRESHOLDS,
) -> SplitHalfAgreement:
    """Motor mu daha iyi uyuşuyor, yoksa saat mi? Eşik ayrık yarıda seçilir."""
    a, b = _halves(obs)
    t_for_a = _best_threshold(b, candidates)   # B'de seç → A'da ölç
    t_for_b = _best_threshold(a, candidates)
    eng_a, eng_b = agreement(a), agreement(b)
    base_a = minute_rule(a, t_for_a) if t_for_a is not None else agreement([])
    base_b = minute_rule(b, t_for_b) if t_for_b is not None else agreement([])

    def _mean(x: float | None, y: float | None) -> float | None:
        vals = [v for v in (x, y) if v is not None]
        return round(sum(vals) / len(vals), 3) if vals else None

    eng_f1 = _mean(eng_a.f1, eng_b.f1)
    base_f1 = _mean(base_a.f1, base_b.f1)

    if len(a) < MIN_TICKS_PER_HALF or len(b) < MIN_TICKS_PER_HALF:
        verdict = "yetersiz veri"
        note = (f"yarılar {len(a)}/{len(b)} tik — hüküm için her yarıda en az "
                f"{MIN_TICKS_PER_HALF} gerekir")
    elif eng_f1 is None or base_f1 is None:
        verdict = "yetersiz veri"
        note = "bir kolda hiç bayrak ya da hiç hamle yok — F1 tanımsız"
    elif eng_f1 - base_f1 >= MIN_F1_GAIN:
        verdict = "taban çizgisini geçiyor"
        note = (f"motor F1 {eng_f1:.2f} vs saat-kuralı F1 {base_f1:.2f} "
                f"(eşikler {t_for_a:.0f}/{t_for_b:.0f} dk, ayrık yarıda seçildi)")
    elif base_f1 - eng_f1 >= MIN_F1_GAIN:
        verdict = "taban çizgisinin altında"
        note = (f"motor F1 {eng_f1:.2f} vs saat-kuralı F1 {base_f1:.2f} — "
                f"yalnız dakikaya bakmak motordan daha çok uyuşuyor")
    else:
        verdict = "taban çizgisiyle aynı"
        note = (f"motor F1 {eng_f1:.2f} vs saat-kuralı F1 {base_f1:.2f} — fark "
                f"±{MIN_F1_GAIN:.2f} bandında; motor saatten fazlasını bilmiyor")

    return SplitHalfAgreement(
        engine_a=eng_a, engine_b=eng_b, baseline_a=base_a, baseline_b=base_b,
        threshold_for_a=t_for_a, threshold_for_b=t_for_b,
        engine_f1=eng_f1, baseline_f1=base_f1, verdict=verdict, note=note,
    )


def lead_times(
    coach_minutes: dict[int, Sequence[float]],
    engine_flag_minutes: dict[int, Sequence[float]],
    *, lookback_min: float = 15.0,
) -> LeadTimeStat:
    """Her gerçek hamle için önceki `lookback` dakikadaki EN ERKEN motor bayrağı."""
    leads: list[float] = []
    moves = 0
    for match_id, minutes in coach_minutes.items():
        flags = sorted(engine_flag_minutes.get(match_id, ()))
        for m in minutes:
            moves += 1
            prior = [f for f in flags if m - lookback_min <= f < m]
            if prior:
                leads.append(m - prior[0])
    covered = len(leads)
    srt = sorted(leads)
    median = None
    if srt:
        mid = len(srt) // 2
        median = srt[mid] if len(srt) % 2 else (srt[mid - 1] + srt[mid]) / 2
    return LeadTimeStat(
        moves=moves, covered=covered,
        coverage=None if not moves else round(covered / moves, 3),
        mean_lead_min=None if not leads else round(sum(leads) / covered, 1),
        median_lead_min=None if median is None else round(median, 1),
    )


# --------------------------------------------------------------------------- #
# Elit zamanlama önseli — "antrenör bu durumda değiştirir mi?" tablosu
# --------------------------------------------------------------------------- #

def _band(minute: float) -> int:
    return sum(1 for edge in PRIOR_MINUTE_BANDS if minute >= edge)


def _cell(st: TickState) -> tuple[int, str, int]:
    return _band(st.minute), st.score_state, min(st.subs_used, PRIOR_MAX_SUBS)


def fit_timing_prior(
    states: Sequence[TickState], *, thresholds: Sequence[float] = PRIOR_THRESHOLDS,
) -> TimingPrior:
    """Hücre başına Laplace düzeltmeli oran; karar eşiği eğitim kümesinde F1'e göre.

    Eşik de eğitimde seçilir — test yarısına hiçbir şey sızmaz.
    """
    hits: dict[tuple[int, str, int], list[int]] = {}
    for st in states:
        hits.setdefault(_cell(st), [0, 0])
        hits[_cell(st)][0] += int(st.coach_acted)
        hits[_cell(st)][1] += 1
    table = {c: (a + PRIOR_LAPLACE) / (n + 2 * PRIOR_LAPLACE) for c, (a, n) in hits.items()}

    best_t, best_f1 = thresholds[0], -1.0
    for t in thresholds:
        f1 = agreement(apply_timing_prior(TimingPrior(table, t, len(states)), states)).f1
        if f1 is not None and f1 > best_f1:
            best_t, best_f1 = t, f1
    return TimingPrior(table=table, threshold=best_t, fitted_on=len(states))


def apply_timing_prior(
    prior: TimingPrior, states: Iterable[TickState],
) -> list[TickObservation]:
    """Görülmemiş hücre → 0.5 (bilinmiyor); eşik ≥ ise bayrak."""
    return [
        TickObservation(
            st.match_external_id, st.minute,
            prior.table.get(_cell(st), 0.5) >= prior.threshold, st.coach_acted,
        )
        for st in states
    ]


def split_half_timing_prior(states: Sequence[TickState]) -> SplitHalfAgreement:
    """Önsel ÖTEKİ yarıda öğrenilir, bu yarıda ölçülür; taban yine saat-kuralı.

    `engine_*` alanları burada önseli taşır (kıyas yapısı aynı olsun diye).
    """
    obs = [TickObservation(s.match_external_id, s.minute, False, s.coach_acted) for s in states]
    a_obs, _ = _halves(obs)
    a_ids = {o.match_external_id for o in a_obs}
    a = [s for s in states if s.match_external_id in a_ids]
    b = [s for s in states if s.match_external_id not in a_ids]
    prior_for_a = fit_timing_prior(b)
    prior_for_b = fit_timing_prior(a)
    merged = apply_timing_prior(prior_for_a, a) + apply_timing_prior(prior_for_b, b)
    return split_half_agreement(merged)


# --------------------------------------------------------------------------- #
# "Kim" — antrenörün çıkardığı oyuncu motorun listesinde miydi?
# --------------------------------------------------------------------------- #

def who_agreement(samples: Sequence[WhoSample], *, k: int = WHO_TOP_K) -> WhoStat:
    """İsabet@1 / isabet@k vs rastgele sahadaki oyuncu taban çizgisi.

    Taban analitik: sahada n oyuncu varsa rastgele seçim 1/n (ve k/n) tutturur.
    Kaleci dahil sayıldığından taban hafif düşüktür; bu belirsizlik hükme değil
    nota yazılır.
    """
    rows = [r for r in samples if r.on_pitch]
    n = len(rows)
    if n == 0:
        return WhoStat(0, None, None, None, None, None, "yetersiz veri", "gerçek değişiklik yok")
    hit1 = sum(1 for r in rows if r.candidates and r.candidates[0] == r.player_off) / n
    hitk = sum(1 for r in rows if r.player_off in r.candidates[:k]) / n
    base1 = sum(1.0 / len(r.on_pitch) for r in rows) / n
    basek = sum(min(1.0, k / len(r.on_pitch)) for r in rows) / n
    cand_total = sum(len(r.candidates[:k]) for r in rows)
    off_pitch = sum(1 for r in rows for c in r.candidates[:k] if c not in r.on_pitch)
    off_rate = None if cand_total == 0 else round(off_pitch / cand_total, 3)

    if n < MIN_SAMPLES:
        verdict = "yetersiz veri"
        note = f"n={n} < {MIN_SAMPLES}"
    elif hitk - basek >= WHO_MIN_GAIN:
        verdict = "taban çizgisini geçiyor"
        note = (f"isabet@{k} {hitk:.0%} vs rastgele {basek:.0%} — motor çıkacak oyuncuyu "
                f"tesadüften iyi biliyor")
    elif basek - hitk >= WHO_MIN_GAIN:
        verdict = "taban çizgisinin altında"
        note = (f"isabet@{k} {hitk:.0%} vs rastgele {basek:.0%} — motorun listesi "
                f"rastgeleden KÖTÜ")
    else:
        verdict = "taban çizgisiyle aynı"
        note = f"isabet@{k} {hitk:.0%} vs rastgele {basek:.0%} — fark ±{WHO_MIN_GAIN:.2f} bandında"
    if off_rate:
        note += f"; adayların {off_rate:.0%}'i hamle anında sahada değildi"
    return WhoStat(
        n=n, hit_at_1=round(hit1, 3), hit_at_k=round(hitk, 3),
        baseline_at_1=round(base1, 3), baseline_at_k=round(basek, 3),
        off_pitch_candidate_rate=off_rate, verdict=verdict, note=note,
    )


def fit_who_prior(states: Sequence[WhoState]) -> WhoPrior:
    """Hücre başına: çıkan / sahada olan (Laplace düzeltmeli)."""
    off: dict[tuple[str, bool], int] = {}
    seen: dict[tuple[str, bool], int] = {}
    for st in states:
        for c in st.candidates:
            key = (c.group, c.starter)
            seen[key] = seen.get(key, 0) + 1
            if c.player_id == st.player_off:
                off[key] = off.get(key, 0) + 1
    table = {k: (off.get(k, 0) + PRIOR_LAPLACE) / (n + 2 * PRIOR_LAPLACE)
             for k, n in seen.items()}
    return WhoPrior(table=table, fitted_on=len(states))


def apply_who_prior(prior: WhoPrior, state: WhoState) -> tuple[int, ...]:
    """Adayları P(çıkar)'a göre sırala; görülmemiş hücre 0.5 (bilinmiyor)."""
    ranked = sorted(
        state.candidates,
        key=lambda c: (-prior.table.get((c.group, c.starter), 0.5), c.player_id),
    )
    return tuple(c.player_id for c in ranked)


def split_half_who_prior(states: Sequence[WhoState], *, k: int = WHO_TOP_K) -> WhoStat:
    """Önsel ÖTEKİ yarıda öğrenilir, bu yarıda isabet@k ölçülür; taban rastgele."""
    ids = sorted({s.match_external_id for s in states})
    a_ids = {m for i, m in enumerate(ids) if i % 2 == 0}
    a = [s for s in states if s.match_external_id in a_ids]
    b = [s for s in states if s.match_external_id not in a_ids]
    prior_for_a, prior_for_b = fit_who_prior(b), fit_who_prior(a)
    samples = [
        WhoSample(s.player_off, apply_who_prior(pr, s), tuple(c.player_id for c in s.candidates))
        for half, pr in ((a, prior_for_a), (b, prior_for_b)) for s in half
    ]
    return who_agreement(samples, k=k)


# --------------------------------------------------------------------------- #
# Şekil seçiciliği — "şekil ayarla" önerisi gerçekten seçici mi?
# --------------------------------------------------------------------------- #

def selectivity(obs: Iterable[TickObservation]) -> SelectivityStat:
    """Bayrak KAÇ tikte yandı ve yandığında haklı çıkma oranı tabanın kaç katı?

    F1 seçicilik sorusunda yanıltır: hedef nadirse (taban ~%20) her tike bayrak
    kaldırmak F1'i yükseltir — hep-evet F1 0.35, seçici bir kural 0.33 çıkabilir.
    Kaldırma (lift = precision / taban oranı) bu tuzağa düşmez: 1.0 demek
    "bayrak hiçbir şey bilmiyor" demektir. Bayrak oranı da bunu kaç öneriyle
    yaptığını gösterir; ikisi birlikte okunur.
    """
    st = agreement(obs)
    base = st.act_rate
    lift = None if st.precision is None or not base else round(st.precision / base, 3)
    return SelectivityStat(
        n=st.n, flagged=st.tp + st.fp, flag_rate=st.flag_rate, base_rate=base,
        precision=st.precision, recall=st.recall, f1=st.f1, lift=lift,
    )


def _shape_cell(st: ShapeState) -> tuple[int, str, int]:
    return _band(st.minute), st.score_state, min(st.subs_used, PRIOR_MAX_SUBS)


def _shape_obs(
    states: Iterable[ShapeState], flag: Callable[[ShapeState], bool],
) -> list[TickObservation]:
    return [TickObservation(s.match_external_id, s.minute, flag(s), s.coach_acted)
            for s in states]


def _gated(
    table: dict[tuple[int, str, int], float], prior_t: float, support_t: int,
) -> Callable[[ShapeState], bool]:
    return lambda s: (s.engine_flag
                      and table.get(_shape_cell(s), 0.5) >= prior_t
                      and s.support_count >= support_t)


def _shape_budget_met(stat: SelectivityStat) -> bool:
    """Gösterim için yuvarlanan flag_rate yerine gerçek örnek sayısını kullan."""
    return stat.n > 0 and stat.flagged >= SHAPE_MIN_FLAG_RATE * stat.n


def fit_shape_prior(
    states: Sequence[ShapeState], *,
    prior_thresholds: Sequence[float] = SHAPE_PRIOR_THRESHOLDS,
    support_thresholds: Sequence[int] = SHAPE_SUPPORT_THRESHOLDS,
) -> ShapePrior:
    """Hücre oranı (Laplace) + iki eşik; eşikler eğitimde SEÇİCİLİĞE göre seçilir.

    Ölçüt F1 DEĞİL: en az `SHAPE_MIN_FLAG_RATE` bayrak bütçesi harcayan adaylar
    arasında en yüksek precision. F1'e göre seçmek bütçeyi sonuna kadar harcayıp
    seçiciliği ortadan kaldırırdı (bkz. `selectivity`). Alt bütçe sınırı, bir
    avuç bayrakla şişmiş precision'ın kazanmasını engeller. Uygun aday yoksa
    eşikler None olur; bu model bayrak üretemez.
    """
    hits: dict[tuple[int, str, int], list[int]] = {}
    for st in states:
        cell = _shape_cell(st)
        hits.setdefault(cell, [0, 0])
        hits[cell][0] += int(st.coach_acted)
        hits[cell][1] += 1
    table = {c: (a + PRIOR_LAPLACE) / (n + 2 * PRIOR_LAPLACE) for c, (a, n) in hits.items()}

    best: tuple[float | None, int | None] = (None, None)
    best_score = -1.0
    for t in prior_thresholds:
        for q in support_thresholds:
            s = selectivity(_shape_obs(states, _gated(table, t, q)))
            score = (s.precision or 0.0) if _shape_budget_met(s) else -1.0
            if score > best_score:
                best, best_score = (t, q), score
    return ShapePrior(table=table, threshold=best[0], support_threshold=best[1],
                      fitted_on=len(states))


def apply_shape_gate(
    prior: ShapePrior, states: Iterable[ShapeState],
) -> list[TickObservation]:
    """Motorun ham bayrağını önsel ve destek eşiğiyle KISAR; görülmemiş hücre 0.5."""
    if prior.threshold is None or prior.support_threshold is None:
        return _shape_obs(states, lambda s: False)
    return _shape_obs(states, _gated(prior.table, prior.threshold, prior.support_threshold))


def split_half_shape_gate(states: Sequence[ShapeState]) -> ShapeGate:
    """Kapı ÖTEKİ yarıda öğrenilir, bu yarıda ölçülür — önce/sonra yan yana.

    Hüküm ölçütü kaldırma: ham bayrak tabanla aynı orandaysa hiçbir şey
    bilmiyordur. Kapılı bayrak İKİ yarıda da `SHAPE_MIN_LIFT` kadar kaldırırsa
    "seçici"; yalnız birinde tutuyorsa "kararsız" — tek yarıda tutan fark
    ölçüm sayılmaz. Eğitimde uygun aday ve kontrol yarılarında yeterli bayrak
    bütçesi yoksa kaldırma yüksek olsa bile hüküm verilmez.
    """
    ids = sorted({s.match_external_id for s in states})
    a_ids = {m for i, m in enumerate(ids) if i % 2 == 0}
    a = [s for s in states if s.match_external_id in a_ids]
    b = [s for s in states if s.match_external_id not in a_ids]
    raw_a = selectivity(_shape_obs(a, lambda s: s.engine_flag))
    raw_b = selectivity(_shape_obs(b, lambda s: s.engine_flag))
    if len(a) < MIN_TICKS_PER_HALF or len(b) < MIN_TICKS_PER_HALF:
        empty = ShapePrior({}, None, None, 0)
        return ShapeGate(
            raw_a=raw_a, raw_b=raw_b, gated_a=selectivity([]), gated_b=selectivity([]),
            prior_for_a=empty, prior_for_b=empty, verdict="yetersiz veri",
            note=(f"yarılar {len(a)}/{len(b)} tik — hüküm için her yarıda en az "
                  f"{MIN_TICKS_PER_HALF} gerekir"),
        )
    prior_for_a, prior_for_b = fit_shape_prior(b), fit_shape_prior(a)
    gated_a = selectivity(apply_shape_gate(prior_for_a, a))
    gated_b = selectivity(apply_shape_gate(prior_for_b, b))

    ga, gb = gated_a.lift, gated_b.lift
    if prior_for_a.threshold is None or prior_for_b.threshold is None:
        verdict = "yetersiz veri"
        note = ("bir eğitim yarısında bayrak bütçesini karşılayan aday yok "
                f"— en az %{SHAPE_MIN_FLAG_RATE * 100:g} gerekir")
    elif not _shape_budget_met(gated_a) or not _shape_budget_met(gated_b):
        verdict = "yetersiz veri"
        note = (f"kontrol yarılarında bayrak {gated_a.flagged}/{gated_a.n} ve "
                f"{gated_b.flagged}/{gated_b.n} — her yarıda en az "
                f"%{SHAPE_MIN_FLAG_RATE * 100:g} gerekir")
    elif ga is None or gb is None:
        verdict = "yetersiz veri"
        note = "bir yarıda precision veya pozitif hedef taban oranı tanımsız"
    else:
        raw = f"ham bayrak {raw_a.lift}/{raw_b.lift} katıydı"
        if ga >= SHAPE_MIN_LIFT and gb >= SHAPE_MIN_LIFT:
            verdict = "seçici"
            note = f"kapılı bayrak tabanın {ga:.2f}/{gb:.2f} katı isabetli; {raw}"
        elif ga >= SHAPE_MIN_LIFT or gb >= SHAPE_MIN_LIFT:
            verdict = "kararsız"
            note = (f"kaldırma yalnız bir yarıda eşiği geçti ({ga:.2f}/{gb:.2f}); "
                    f"tek yarıda tutan fark ölçüm sayılmaz — {raw}")
        else:
            verdict = "seçici değil"
            note = (f"kapıdan sonra bile kaldırma {ga:.2f}/{gb:.2f} — bayrak taban "
                    f"oranından fazlasını bilmiyor; {raw}")
    return ShapeGate(
        raw_a=raw_a, raw_b=raw_b, gated_a=gated_a, gated_b=gated_b,
        prior_for_a=prior_for_a, prior_for_b=prior_for_b, verdict=verdict, note=note,
    )


# --------------------------------------------------------------------------- #
# Öngörü / kalibrasyon ölçekleri
# --------------------------------------------------------------------------- #

def skill_from_auc(auc: float | None) -> float | None:
    """AUC → 0..100 beceri. 0.5 = 0 (yazı-tura), 1.0 = 100; TERS ilişki 0'a kırpılır."""
    if auc is None:
        return None
    return round(max(0.0, min(1.0, 2.0 * (auc - 0.5))) * 100.0, 1)


def expected_calibration_error(
    samples: Sequence[tuple[float, bool]], *, bins: int = DEFAULT_ECE_BINS,
) -> tuple[float | None, float | None, float | None]:
    """(ECE, ortalama güven, isabet oranı). Bin: eşit genişlik, 0..1.

    ECE = Σ (n_b / n) · |ort_güven_b − isabet_b|. Boş binler atlanır.
    """
    rows = [(float(c), bool(ok)) for c, ok in samples if 0.0 <= c <= 1.0]
    n = len(rows)
    if n == 0:
        return None, None, None
    ece = 0.0
    for i in range(bins):
        lo, hi = i / bins, (i + 1) / bins
        inb = [(c, ok) for c, ok in rows if lo <= c < hi or (i == bins - 1 and c == 1.0)]
        if not inb:
            continue
        conf = sum(c for c, _ in inb) / len(inb)
        hit = sum(1 for _, ok in inb if ok) / len(inb)
        ece += len(inb) / n * abs(conf - hit)
    mean_conf = sum(c for c, _ in rows) / n
    hit_rate = sum(1 for _, ok in rows if ok) / n
    return round(ece, 3), round(mean_conf, 3), round(hit_rate, 3)


# --------------------------------------------------------------------------- #
# Karne
# --------------------------------------------------------------------------- #

def build_scorecard(dimensions: Sequence[Dimension]) -> Scorecard:
    """Boyutları tek başlığa indir — bileşik puan YOK, sayım var.

    Beş boyutun ölçekleri farklı (AUC, ECE, F1, isabet, uplift); tek sayıya
    harmanlamak bir boyutun körlüğünü ötekinin parlaklığıyla örterdi. Başlık
    iki sayım verir: kaç boyut ölçülebildi, kaçı taban çizgisini geçti.
    """
    measurable = sum(1 for d in dimensions if d.measurable)
    beating = sum(1 for d in dimensions if d.measurable and d.verdict == "taban çizgisini geçiyor")
    headline = (f"{len(dimensions)} boyutun {measurable}'i ölçülebildi; "
                f"{beating}'i taban çizgisini geçiyor")
    if measurable and beating == 0:
        headline += " — motor bugün ölçülebilen hiçbir boyutta saatten/yazı-turadan iyi değil"
    return Scorecard(
        dimensions=tuple(dimensions), measurable=measurable,
        beating_baseline=beating, headline=headline,
    )
