"""Karar uplift'i — öneri UYGULANINCA, uygulanmayınca olandan daha mı iyi gidiyor?

## Neden bu motor var

`decision_impact` her kararın öncesi/sonrası farkını ölçer ve `outcome` yazar.
Bu "sonra ne oldu"dur. Külliyatta ölçüldü (502 karar, gerçek maçlar): kararlar
hiç uygulanmadığı için "sonra ne oldu" ile "öneri YÜZÜNDEN ne oldu" birbirinden
ayrılamıyor; 16 aday sinyalin hiçbiri sonucu ayırt etmiyor. Sorun sinyalde
değil, karşı-olgunun yokluğunda.

Bu motor karşı-olguyu kullanır: koçun `applied=True` işaretlediği öneriler
(uygulanan kol) ile `applied=False` işaretledikleri (uygulanmayan kol) aynı
cetvelle ölçülür ve kıyaslanır. Uygulanmayan öneri, aynı durumda "hiçbir şey
yapılmasaydı"nın elimizdeki en yakın gözlemidir.

## Karıştırıcı: ortalamaya dönüş

Cetvel `sonraki − önceki` farkı olduğu için kötü giderken alınan kararlar
sistematik olarak ödüllendirilir. Koç öneriyi daha çok kötü giderken
uygularsa, uygulanan kol ham kıyasta HAKSIZ yere iyi görünür. Bu yüzden
örnekler karar öncesi duruma (`pre`: önceki pencere xG farkı) göre eşit
büyüklükte katmanlara bölünür ve kollar yalnız katman İÇİNDE kıyaslanır.
Katman farkları, kıyaslanabilir çift sayısıyla (`n_a·n_n / n`, Mantel-Haenszel
ağırlığı) tartılarak birleştirilir. Ham fark da raporlanır ki karıştırıcının
ne kadarını yediği görünsün.

## Dürüstlük

- Bir kol boşsa hüküm verilmez: "karşı-olgu yok" / "uygulanan yok".
- `attribution.MIN_SAMPLES` altında "yetersiz veri".
- `MIN_EFFECT` altındaki fark "fark yok" sayılır; eşik kaba bir kuraldır ve
  pilot verisiyle ayarlanır.
- Bu hâlâ gözlemsel bir kıyastır: koç neyi uyguladığını kendi seçer. Katmanlama
  yalnız ölçülen karıştırıcıyı (karar öncesi durum) kontrol eder.

Saf fonksiyon; DB/IO yok.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass

from app.audit import AuditRecord, EngineResult
from app.engine.confidence.attribution import MIN_SAMPLES

ENGINE_NAME = "engine.decision_uplift"
ENGINE_VERSION = "1"

# İsabet oranı farkı (puan) bu değerin altındaysa "fark yok"
MIN_EFFECT = 0.10
DEFAULT_STRATA = 4


@dataclass(frozen=True)
class UpliftSample:
    """Ölçülmüş bir öneri: koç uyguladı mı, sonuç olumlu mu, karar öncesi durum."""

    applied: bool | None          # None = işaretlenmedi → kıyasa girmez
    positive: bool                # outcome == "positive" (negative → False)
    xg_delta: float               # decision_impact.xg_diff_delta (dk başına)
    pre: float                    # karıştırıcı: önceki pencere xG farkı (dk başına)


@dataclass(frozen=True)
class ArmStat:
    n: int
    positive: int
    hit_rate: float | None        # positive / n
    mean_xg_delta: float


@dataclass(frozen=True)
class StratumStat:
    pre_lo: float
    pre_hi: float
    applied: ArmStat
    not_applied: ArmStat
    hit_rate_diff: float | None   # iki kol da doluysa: uygulanan − uygulanmayan


@dataclass(frozen=True)
class DecisionUplift:
    team_external_id: int
    applied: ArmStat
    not_applied: ArmStat
    unknown: int                  # applied=None ölçülmüş öneri — kıyasa girmez
    raw_hit_rate_diff: float | None
    raw_xg_delta_diff: float | None
    stratified_hit_rate_diff: float | None
    strata: tuple[StratumStat, ...]
    verdict: str                  # uplift | TERS | fark yok | yetersiz veri |
                                  # karşı-olgu yok | uygulanan yok | ayrıştırılamıyor
    note: str


def _arm(samples: Sequence[UpliftSample]) -> ArmStat:
    n = len(samples)
    pos = sum(1 for s in samples if s.positive)
    return ArmStat(
        n=n, positive=pos,
        hit_rate=round(pos / n, 3) if n else None,
        mean_xg_delta=round(sum(s.xg_delta for s in samples) / n, 4) if n else 0.0,
    )


def _diff(a: float | None, b: float | None) -> float | None:
    return round(a - b, 3) if a is not None and b is not None else None


def compute_decision_uplift(
    team_external_id: int,
    samples: Sequence[UpliftSample],
    *,
    strata: int = DEFAULT_STRATA,
) -> EngineResult[DecisionUplift]:
    """Uygulanan vs uygulanmayan öneri: ham ve katmanlı isabet farkı + hüküm."""
    marked = [s for s in samples if s.applied is not None]
    unknown = len(samples) - len(marked)
    a_all = [s for s in marked if s.applied]
    n_all = [s for s in marked if not s.applied]
    arm_a, arm_n = _arm(a_all), _arm(n_all)
    raw_hit = _diff(arm_a.hit_rate, arm_n.hit_rate)
    raw_xg = (round(arm_a.mean_xg_delta - arm_n.mean_xg_delta, 4)
              if arm_a.n and arm_n.n else None)

    # Katmanlar: karar öncesi duruma göre sıralı, eşit büyüklükte
    # (`attribution.attribute_stratified` ile aynı bölme kuralı).
    sirali = sorted(marked, key=lambda s: s.pre)
    boyut = max(1, len(sirali) // max(1, strata)) if sirali else 1
    katmanlar: list[StratumStat] = []
    toplam_agirlik = 0.0
    toplam_fark = 0.0
    for i in range(0, len(sirali), boyut):
        katman = sirali[i:i + boyut]
        ka = _arm([s for s in katman if s.applied])
        kn = _arm([s for s in katman if not s.applied])
        fark = _diff(ka.hit_rate, kn.hit_rate)
        katmanlar.append(StratumStat(
            pre_lo=round(katman[0].pre, 4), pre_hi=round(katman[-1].pre, 4),
            applied=ka, not_applied=kn, hit_rate_diff=fark,
        ))
        if fark is None:
            continue                       # tek kollu katman kıyas vermez
        agirlik = ka.n * kn.n / (ka.n + kn.n)
        toplam_fark += fark * agirlik
        toplam_agirlik += agirlik
    strat = (round(toplam_fark / toplam_agirlik, 3)
             if toplam_agirlik > 0 else None)

    if arm_n.n == 0:
        verdict = "karşı-olgu yok"
        note = (f"uygulanmayan öneri kaydı yok (uygulanan {arm_a.n}, işaretsiz "
                f"{unknown}) — 'Uygulamadım' işareti olmadan öneri etkisi "
                f"ölçülemez; ölçülen yalnız 'sonra ne oldu'dur")
    elif arm_a.n == 0:
        verdict = "uygulanan yok"
        note = (f"uygulanan öneri kaydı yok (uygulanmayan {arm_n.n}, işaretsiz "
                f"{unknown}) — kıyas için uygulanan kol gerekir")
    elif len(marked) < MIN_SAMPLES:
        verdict = "yetersiz veri"
        note = (f"n={len(marked)} (uygulanan {arm_a.n} / uygulanmayan {arm_n.n}) — "
                f"hüküm için en az {MIN_SAMPLES} işaretli öneri gerekir")
    elif strat is None:
        verdict = "ayrıştırılamıyor"
        note = ("her katman tek kollu: koç öneriyi hep aynı durumlarda uyguluyor "
                "(ya da hep aynı durumlarda atlıyor); karar öncesi durum "
                "kontrol edilince kıyaslanacak çift kalmıyor — ham fark "
                f"{raw_hit:+.3f} yanıltıcı olabilir")
    elif strat >= MIN_EFFECT:
        verdict = "uplift"
        note = (f"aynı karar öncesi durumda uygulanan öneriler {strat * 100:+.0f} "
                f"puan daha sık olumlu (ham fark {raw_hit:+.3f})")
    elif strat <= -MIN_EFFECT:
        verdict = "TERS"
        note = (f"aynı karar öncesi durumda uygulanan öneriler {strat * 100:+.0f} "
                f"puan daha SEYREK olumlu (ham fark {raw_hit:+.3f}) — öneriler "
                f"zarar veriyor ya da koç yalnız umutsuz durumlarda uyguluyor")
    else:
        verdict = "fark yok"
        note = (f"katmanlı fark {strat:+.3f} — eşik ±{MIN_EFFECT:.2f} içinde; "
                f"uygulamak ile uygulamamak arasında ölçülebilir fark yok "
                f"(ham fark {raw_hit:+.3f})")

    value = DecisionUplift(
        team_external_id=team_external_id,
        applied=arm_a, not_applied=arm_n, unknown=unknown,
        raw_hit_rate_diff=raw_hit, raw_xg_delta_diff=raw_xg,
        stratified_hit_rate_diff=strat, strata=tuple(katmanlar),
        verdict=verdict, note=note,
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="team", subject_id=team_external_id,
        metric="decision_uplift", value=asdict(value),
        inputs={"samples": len(samples), "marked": len(marked),
                "unknown": unknown, "strata": strata},
        formula=(
            "örnekler karar öncesi xG farkına göre eşit katmanlara bölünür; "
            "katman içi (uygulanan isabet − uygulanmayan isabet) farkları "
            "n_a·n_n/(n_a+n_n) ile ağırlıklı ortalanır; "
            f"|fark| ≥ {MIN_EFFECT} → uplift/TERS, n < {MIN_SAMPLES} → yetersiz veri. "
            "Gözlemsel kıyas — koç neyi uyguladığını kendi seçer."
        ),
    )
    return EngineResult(value=value, audit=audit)
