"""Minutes Management — sezon dakika yönetimi + maraton riski tahmini.

Premier League / Süper Lig'de TD'nin yapamadığı en zor karar: kim ne kadar
oynayacak. Bu engine son N hafta dakikalarını + yaş + sakatlık geçmişi +
sonraki maç sıklığına bakar; oyuncu başına "ne kadar oynayabilir" tavsiyesi
verir.

Pure compute. PlayerMinutesInput listesi + opsiyonel meta input.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from app.audit import AuditRecord, EngineResult

ENGINE_NAME = "engine.minutes_management"
ENGINE_VERSION = "1"

# Eşikler — sezon ortalaması × hafta sayısı bazlı
MAX_WEEKLY_MINUTES = 100.0          # tam fit oyuncu için haftalık çatı
HIGH_LOAD_THRESHOLD = 80.0          # son hafta avg ≥80 → yüksek yük
LOW_LOAD_THRESHOLD = 30.0           # son hafta avg <30 → düşük yük
AGE_RISK_VETERAN = 32
AGE_RISK_VERY_YOUNG = 18
INJURY_RECENT_WEEKS = 4

# Maraton (yoğun fikstür) eşiği — sonraki 14 günde maç sayısı
MARATHON_MATCHES = 4


@dataclass(frozen=True)
class PlayerMinutesInput:
    player_external_id: int
    age: int
    weekly_minutes_recent: list[float]  # son N hafta dakikalar
    days_since_last_injury: int | None = None  # None = sakatlık geçmişi bilinmiyor
    matches_next_2_weeks: int = 2       # default normal fikstür


@dataclass(frozen=True)
class PlayerRecommendation:
    player_external_id: int
    age: int
    avg_minutes_recent: float
    total_minutes_recent: float
    load_band: str                      # "düşük" | "normal" | "yüksek" | "kritik"
    rest_advised_next_match: bool
    target_minutes_next_match: int      # öneri (0-90)
    risk_flags: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class MinutesManagementPlan:
    total_players: int
    rest_count: int                     # rotation altı
    high_load_count: int
    marathon_window: bool               # sonraki 14 gün yoğun mu
    recommendations: tuple[PlayerRecommendation, ...]
    summary_advice: str


def _band(avg: float, weeks: int) -> str:
    total = avg * weeks
    if total >= HIGH_LOAD_THRESHOLD * weeks * 1.2:
        return "kritik"
    if avg >= HIGH_LOAD_THRESHOLD:
        return "yüksek"
    if avg <= LOW_LOAD_THRESHOLD:
        return "düşük"
    return "normal"


def _target_minutes(
    band: str, age: int, marathon: bool,
    days_since_injury: int | None,
) -> int:
    """Bir sonraki maç için öneri dakika."""
    base = 90
    if band == "kritik":
        base = 30
    elif band == "yüksek":
        base = 60 if not marathon else 45
    elif band == "düşük":
        base = 90  # az oynamış, sahaya çıkmaya hazır
    # Yaş düzeltmesi
    if age >= AGE_RISK_VETERAN:
        base = max(0, base - 15)
    elif age <= AGE_RISK_VERY_YOUNG:
        base = min(base, 75)  # çok genç → uzun süre fizyolojik risk
    # Yakın sakatlık dönüşü
    if days_since_injury is not None and 0 < days_since_injury <= INJURY_RECENT_WEEKS * 7:
        base = min(base, 60)
    return base


def _risk_flags(p: PlayerMinutesInput, band: str, marathon: bool) -> list[str]:
    flags: list[str] = []
    if band == "kritik":
        flags.append("yorgunluk birikmesi (kritik)")
    if band == "yüksek" and marathon:
        flags.append("yüksek yük + maraton penceresi")
    if p.age >= AGE_RISK_VETERAN:
        flags.append(f"yaş {p.age} → toparlanma yavaş")
    if p.age <= AGE_RISK_VERY_YOUNG:
        flags.append(f"yaş {p.age} → gelişim fizyolojisi")
    if (p.days_since_last_injury is not None
            and 0 < p.days_since_last_injury <= INJURY_RECENT_WEEKS * 7):
        flags.append(f"sakatlık dönüşü ({p.days_since_last_injury} gün önce)")
    return flags


def compute_minutes_management(
    players: Iterable[PlayerMinutesInput],
    *,
    matches_next_2_weeks: int | None = None,
) -> EngineResult[MinutesManagementPlan]:
    """Sezon dakika yönetimi planı."""
    plist = list(players)
    if not plist:
        plan = MinutesManagementPlan(
            total_players=0, rest_count=0, high_load_count=0,
            marathon_window=False, recommendations=(),
            summary_advice="Oyuncu listesi boş",
        )
        return EngineResult(value=plan, audit=AuditRecord(
            engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
            subject_type="team", subject_id=0, metric="minutes_management",
            value={"total_players": 0},
            inputs={}, formula="empty",
        ))

    # Maraton penceresi: toplam fikstür ortalaması
    if matches_next_2_weeks is not None:
        global_marathon = matches_next_2_weeks >= MARATHON_MATCHES
    else:
        avg_fixtures = sum(p.matches_next_2_weeks for p in plist) / len(plist)
        global_marathon = avg_fixtures >= MARATHON_MATCHES

    recs: list[PlayerRecommendation] = []
    rest = 0
    high = 0
    for p in plist:
        recent = p.weekly_minutes_recent or []
        avg = sum(recent) / len(recent) if recent else 0.0
        total = sum(recent)
        band = _band(avg, max(1, len(recent)))
        target = _target_minutes(band, p.age, global_marathon,
                                  p.days_since_last_injury)
        rest_advised = band in ("kritik", "yüksek") and global_marathon
        if rest_advised:
            rest += 1
        if band in ("yüksek", "kritik"):
            high += 1
        recs.append(PlayerRecommendation(
            player_external_id=p.player_external_id,
            age=p.age,
            avg_minutes_recent=round(avg, 1),
            total_minutes_recent=round(total, 1),
            load_band=band,
            rest_advised_next_match=rest_advised,
            target_minutes_next_match=target,
            risk_flags=tuple(_risk_flags(p, band, global_marathon)),
        ))

    if rest == 0 and high == 0:
        summary = "Tüm kadro normal yük altında — rotasyon zorunlu değil"
    else:
        summary = (
            f"{high} oyuncuda yüksek yük; "
            f"{rest} oyuncuya bir sonraki maç dinlendirme tavsiyesi"
        )
        if global_marathon:
            summary += " · maraton penceresi (≥4 maç/14 gün)"

    plan = MinutesManagementPlan(
        total_players=len(plist), rest_count=rest, high_load_count=high,
        marathon_window=global_marathon,
        recommendations=tuple(recs),
        summary_advice=summary,
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="team", subject_id=0,
        metric="minutes_management",
        value={
            "total_players": len(plist),
            "rest_count": rest, "high_load_count": high,
            "marathon_window": global_marathon,
            "summary_advice": summary,
        },
        inputs={
            "matches_next_2_weeks_override": matches_next_2_weeks,
            "thresholds": {
                "high_load": HIGH_LOAD_THRESHOLD,
                "low_load": LOW_LOAD_THRESHOLD,
                "marathon_matches": MARATHON_MATCHES,
                "age_veteran": AGE_RISK_VETERAN,
                "age_young": AGE_RISK_VERY_YOUNG,
            },
        },
        formula=(
            "band: avg ≥80 yüksek, ≤30 düşük, kritik=avg*weeks≥%120 hafta avg; "
            "target: kritik→30, yüksek→60 (maraton 45), genç ≤75, veteran -15, "
            "sakatlık ≤60"
        ),
    )
    return EngineResult(value=plan, audit=audit)
