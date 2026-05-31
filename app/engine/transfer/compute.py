"""Transfer zinciri engine'leri — değerleme, yedek bulma, kontrat riski, uyum.

Pilot kulüplerin "oyuncu sat / al" kararı için dört saf hesap:

1. `compute_transfer_value` — performans + yaş eğrisi + süreklilikten 0-100
   göreli DEĞER SKORU (€ ücreti DEĞİL; piyasa-ücreti verisi yok → açık proxy).
2. `compute_replacement_options` — gidecek oyuncuya `engine.player_similarity`
   benzerlik + müsaitlik + yaş ile sıralanmış yedek adayları.
3. `compute_contract_risk` — kontrat bitişi + yaş + değer + oynama süresinden
   "bedava kaybetme / yenile / sat" riski.
4. `compute_recruitment_fit` — aday oyuncunun takım ihtiyacına (pozisyon +
   stil/performans hedefi) uyum skoru.

Tasarım: dört engine tek pakette gruplandı çünkü ortak yaş-eğrisi ve skor
yardımcılarını paylaşıyorlar; her biri ayrı `ENGINE_NAME` ile audit'lenir.

Sınırlamalar (önemli — kullanıcıya iletilmeli):
- Gerçek transfer ücreti / piyasa değeri verisi YOK; skorlar performans-temelli
  GÖRELİ proxy. "€20M değerinde" demez, "elit değer bandı" der.
- Performans sinyali API-Football maç rating'i + per-90 katkıya dayanır;
  pozisyon-spesifik ağırlık yok (Faz: pozisyon profilleri).
- Yaş eğrisi futbol literatürü ortalaması (zirve ~24-27).

Engine kuralı: saf hesap; girdi düz değerler/profiller, çıktı `EngineResult`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from app.audit import AuditRecord, ConfidenceInfo, EngineResult
from app.engine.confidence import score_confidence

# Yaş eğrisi — zirve aralığı ve kenar çarpanları (göreli değer için).
_PEAK_AGE_LOW = 24
_PEAK_AGE_HIGH = 27
# Rating normalizasyon bandı (API-Football maç rating'i tipik 6.0..8.0).
_RATING_FLOOR = 6.0
_RATING_CEIL = 8.0
# "Tam sezon" referans dakikası (süreklilik bileşeni için).
_FULL_SEASON_MINUTES = 2700  # ~30 maç × 90 dk


def _clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)


def _age_factor(age: int | None) -> float:
    """Yaşa göre değer çarpanı 0..1 (zirvede 1.0, kenarlarda azalır)."""
    if age is None:
        return 0.7  # bilinmiyor → nötr-yüksek
    if _PEAK_AGE_LOW <= age <= _PEAK_AGE_HIGH:
        return 1.0
    if age < _PEAK_AGE_LOW:
        # Genç: her yıl zirveden uzaklık -0.06 (potansiyel yine de yüksek)
        return _clamp01(1.0 - 0.06 * (_PEAK_AGE_LOW - age))
    # Yaşlı: her yıl -0.09 (düşüş daha hızlı)
    return _clamp01(1.0 - 0.09 * (age - _PEAK_AGE_HIGH))


def _rating_term(rating_avg: float) -> float:
    """Maç rating'ini 0..1'e normalize et."""
    return _clamp01((rating_avg - _RATING_FLOOR) / (_RATING_CEIL - _RATING_FLOOR))


# --------------------------------------------------------------------------- #
# 1) Transfer value estimator
# --------------------------------------------------------------------------- #

ENGINE_VALUE = "engine.transfer_value_estimator"


@dataclass(frozen=True)
class TransferValueReport:
    player_external_id: int
    value_score: float            # 0..100 göreli değer
    tier: str                     # elite/high/solid/squad/fringe
    age: int | None
    age_factor: float
    rating_avg: float
    rating_term: float
    minutes_played: int
    availability_term: float
    low_confidence: bool
    note: str


def _value_tier(score: float) -> str:
    if score >= 80:
        return "elite"
    if score >= 62:
        return "high"
    if score >= 42:
        return "solid"
    if score >= 22:
        return "squad"
    return "fringe"


def compute_transfer_value(
    player_external_id: int,
    *,
    rating_avg: float,
    minutes_played: int,
    matches_played: int,
    age: int | None = None,
) -> EngineResult[TransferValueReport]:
    """Performans + yaş + süreklilikten 0-100 göreli değer skoru.

    value_score = 100 · (0.55·rating + 0.25·age + 0.20·availability)
    """
    rt = _rating_term(rating_avg)
    af = _age_factor(age)
    avail = _clamp01(minutes_played / _FULL_SEASON_MINUTES)
    score = 100.0 * (0.55 * rt + 0.25 * af + 0.20 * avail)
    low_conf = matches_played < 5 or minutes_played < 450

    report = TransferValueReport(
        player_external_id=player_external_id,
        value_score=round(score, 1),
        tier=_value_tier(score),
        age=age,
        age_factor=round(af, 3),
        rating_avg=round(rating_avg, 2),
        rating_term=round(rt, 3),
        minutes_played=minutes_played,
        availability_term=round(avail, 3),
        low_confidence=low_conf,
        note="Göreli performans-temelli değer proxy'si — gerçek € ücreti değil.",
    )
    audit = AuditRecord(
        engine=ENGINE_VALUE, engine_version="1",
        subject_type="player", subject_id=player_external_id,
        metric="transfer_value_score", value=asdict(report),
        inputs={
            "rating_avg": rating_avg, "minutes_played": minutes_played,
            "matches_played": matches_played, "age": age,
            "peak_age": [_PEAK_AGE_LOW, _PEAK_AGE_HIGH],
        },
        formula="100·(0.55·rating_term + 0.25·age_factor + 0.20·availability)",
    )
    conf = score_confidence(sample_size=matches_played, magnitude=rt)
    return EngineResult(
        value=report, audit=audit,
        confidence=ConfidenceInfo(conf.score, conf.label, conf.drivers),
    )


# --------------------------------------------------------------------------- #
# 2) Replacement finder
# --------------------------------------------------------------------------- #

ENGINE_REPLACEMENT = "engine.replacement_finder"


@dataclass(frozen=True)
class ReplacementCandidate:
    player_external_id: int
    similarity: float       # -1..1 (player_similarity'den)
    minutes_played: int
    age: int | None
    fit_score: float        # 0..100 birleşik
    flags: tuple[str, ...]  # "young", "high_minutes", "aging" vb.


@dataclass(frozen=True)
class ReplacementReport:
    target_player_id: int
    candidates_considered: int
    top_candidates: list[ReplacementCandidate]


def compute_replacement_options(
    target_player_id: int,
    candidates: list[dict],
    *,
    top_n: int = 5,
    min_similarity: float = 0.3,
) -> EngineResult[ReplacementReport]:
    """Gidecek oyuncuya benzer + müsait + uygun-yaş yedekleri sırala.

    `candidates`: `[{player_external_id, similarity, minutes_played, age?}]`
    (similarity `engine.player_similarity`'den gelir). fit_score benzerlik +
    süreklilik + yaş eğrisini birleştirir.
    """
    scored: list[ReplacementCandidate] = []
    for c in candidates:
        sim = float(c.get("similarity", 0.0))
        if sim < min_similarity:
            continue
        pid = int(c["player_external_id"])
        minutes = int(c.get("minutes_played", 0))
        age = c.get("age")
        age = int(age) if age is not None else None
        avail = _clamp01(minutes / _FULL_SEASON_MINUTES)
        af = _age_factor(age)
        # Benzerlik baskın (0.6), müsaitlik (0.25), yaş (0.15)
        fit = 100.0 * (0.60 * _clamp01(sim) + 0.25 * avail + 0.15 * af)
        flags: list[str] = []
        if age is not None and age <= 21:
            flags.append("young_prospect")
        if age is not None and age >= 30:
            flags.append("aging")
        if avail >= 0.8:
            flags.append("high_availability")
        scored.append(ReplacementCandidate(
            player_external_id=pid, similarity=round(sim, 4),
            minutes_played=minutes, age=age,
            fit_score=round(fit, 1), flags=tuple(flags),
        ))
    scored.sort(key=lambda c: c.fit_score, reverse=True)
    top = scored[: max(1, top_n)]

    report = ReplacementReport(
        target_player_id=target_player_id,
        candidates_considered=len(candidates),
        top_candidates=top,
    )
    audit = AuditRecord(
        engine=ENGINE_REPLACEMENT, engine_version="1",
        subject_type="player", subject_id=target_player_id,
        metric="replacement_options", value=asdict(report),
        inputs={
            "candidates_considered": len(candidates),
            "min_similarity": min_similarity, "top_n": top_n,
        },
        formula="fit = 100·(0.60·similarity + 0.25·availability + 0.15·age_factor)",
    )
    conf = score_confidence(
        sample_size=len(scored),
        magnitude=top[0].fit_score / 100.0 if top else 0.0,
    )
    return EngineResult(
        value=report, audit=audit,
        confidence=ConfidenceInfo(conf.score, conf.label, conf.drivers),
    )


# --------------------------------------------------------------------------- #
# 3) Contract risk
# --------------------------------------------------------------------------- #

ENGINE_CONTRACT = "engine.contract_risk"


@dataclass(frozen=True)
class ContractRiskReport:
    player_external_id: int
    days_remaining: int
    value_score: float
    age: int | None
    risk_level: str          # critical/high/medium/low
    risk_score: float        # 0..100
    recommendation: str      # renew_now / sell_to_recoup / monitor / let_expire
    rationale: str


def compute_contract_risk(
    player_external_id: int,
    *,
    days_remaining: int,
    value_score: float,
    age: int | None = None,
    minutes_played: int = 0,
) -> EngineResult[ContractRiskReport]:
    """Kontrat bitişi + oyuncu değeri + yaştan bedava-kaybetme riski + tavsiye.

    Yüksek değerli + kısa süreli kontrat = en yüksek risk (bedava gidebilir).
    """
    # Yakınlık terimi: <=180g → 1.0; >=730g → 0.0 (lineer)
    if days_remaining <= 180:
        proximity = 1.0
    elif days_remaining >= 730:
        proximity = 0.0
    else:
        proximity = (730 - days_remaining) / (730 - 180)
    value_term = _clamp01(value_score / 100.0)
    # Risk: değerli oyuncuyu kısa sürede kaybetmek kötü
    risk = 100.0 * (0.65 * proximity + 0.35 * value_term)

    if risk >= 70:
        level = "critical"
    elif risk >= 50:
        level = "high"
    elif risk >= 30:
        level = "medium"
    else:
        level = "low"

    # Tavsiye: değerli + kısa kontrat → yenile; yaşlı + kısa → sat/bırak
    aging = age is not None and age >= 30
    if days_remaining <= 365 and value_term >= 0.6 and not aging:
        rec, why = "renew_now", "Yüksek değerli, kontrat kısa — bedava kaybetme riski."
    elif days_remaining <= 365 and aging:
        rec, why = "sell_to_recoup", "Yaşlanan oyuncu, kontrat kısa — değer düşmeden sat."
    elif days_remaining <= 540 and value_term >= 0.4:
        rec, why = "monitor", "Orta vadede yenileme görüşmesi planla."
    elif value_term < 0.25 and days_remaining <= 365:
        rec, why = "let_expire", "Düşük katkı — uzatma maliyeti gerekçesiz."
    else:
        rec, why = "monitor", "Acil risk yok; periyodik gözden geçir."

    report = ContractRiskReport(
        player_external_id=player_external_id,
        days_remaining=days_remaining,
        value_score=round(value_score, 1),
        age=age,
        risk_level=level,
        risk_score=round(risk, 1),
        recommendation=rec,
        rationale=why,
    )
    audit = AuditRecord(
        engine=ENGINE_CONTRACT, engine_version="1",
        subject_type="player", subject_id=player_external_id,
        metric="contract_risk", value=asdict(report),
        inputs={
            "days_remaining": days_remaining, "value_score": value_score,
            "age": age, "minutes_played": minutes_played,
        },
        formula="risk = 100·(0.65·proximity + 0.35·value_term); proximity=180..730g lineer",
    )
    conf = score_confidence(sample_size=max(1, minutes_played // 90), magnitude=value_term)
    return EngineResult(
        value=report, audit=audit,
        confidence=ConfidenceInfo(conf.score, conf.label, conf.drivers),
    )


# --------------------------------------------------------------------------- #
# 4) Recruitment fit
# --------------------------------------------------------------------------- #

ENGINE_RECRUITMENT = "engine.recruitment_fit"


@dataclass(frozen=True)
class RecruitmentFitReport:
    player_external_id: int
    position_match: bool
    fit_score: float          # 0..100
    style_alignment: float    # 0..1 hedef stil metriklerine yakınlık
    value_term: float
    verdict: str              # strong_fit / possible_fit / weak_fit
    rationale: str


def compute_recruitment_fit(
    player_external_id: int,
    *,
    candidate_position: str | None,
    needed_position: str,
    candidate_metrics: dict[str, float],
    target_metrics: dict[str, float],
    value_score: float = 50.0,
) -> EngineResult[RecruitmentFitReport]:
    """Aday oyuncunun takım ihtiyacına uyumu (pozisyon + stil + değer).

    `*_metrics`: aynı anahtarlı per-90 stil profilleri (örn. {"pass_pct":..,
    "shots_p90":..}). style_alignment = 1 - normalize(L1 mesafe).
    """
    position_match = (
        candidate_position is not None
        and candidate_position.upper() == needed_position.upper()
    )
    # Stil hizası: ortak anahtarlarda göreli mutlak fark ortalaması
    keys = set(candidate_metrics) & set(target_metrics)
    if keys:
        diffs = []
        for k in keys:
            tgt = target_metrics[k]
            denom = abs(tgt) if abs(tgt) > 1e-9 else 1.0
            diffs.append(min(1.0, abs(candidate_metrics[k] - tgt) / denom))
        style_alignment = 1.0 - sum(diffs) / len(diffs)
    else:
        style_alignment = 0.5  # ortak metrik yok → nötr
    style_alignment = _clamp01(style_alignment)
    value_term = _clamp01(value_score / 100.0)

    pos_term = 1.0 if position_match else 0.4
    fit = 100.0 * (0.45 * pos_term + 0.35 * style_alignment + 0.20 * value_term)

    if position_match and fit >= 65:
        verdict, why = "strong_fit", "Pozisyon + stil + değer uyumlu."
    elif fit >= 50:
        verdict, why = "possible_fit", "Kısmi uyum; ek scouting önerilir."
    else:
        verdict, why = "weak_fit", "İhtiyaç profiline düşük uyum."

    report = RecruitmentFitReport(
        player_external_id=player_external_id,
        position_match=position_match,
        fit_score=round(fit, 1),
        style_alignment=round(style_alignment, 3),
        value_term=round(value_term, 3),
        verdict=verdict,
        rationale=why,
    )
    audit = AuditRecord(
        engine=ENGINE_RECRUITMENT, engine_version="1",
        subject_type="player", subject_id=player_external_id,
        metric="recruitment_fit", value=asdict(report),
        inputs={
            "candidate_position": candidate_position,
            "needed_position": needed_position,
            "common_metric_keys": sorted(keys),
            "value_score": value_score,
        },
        formula="fit = 100·(0.45·position + 0.35·style_alignment + 0.20·value_term)",
    )
    conf = score_confidence(sample_size=len(keys), magnitude=style_alignment)
    return EngineResult(
        value=report, audit=audit,
        confidence=ConfidenceInfo(conf.score, conf.label, conf.drivers),
    )
