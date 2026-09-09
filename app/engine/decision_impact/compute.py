"""Karar etkisi — teknik direktörün hamlesi işe yaradı mı? (post-match learning)

`decisions` tablosu koçun maç-içi hamlelerini (ikame, diziliş, pres yüksekliği…)
zaten kaydediyor; bu motor her kararın ÖNCESİ ve SONRASI pencerelerini ölçüp
etkiyi sayıya döker, sonra `outcome` alanına yazılabilecek bir hüküm üretir.
Hüküm `engine.confidence` üzerinden context_engine'in güven skoruna geri besler:
sistem, bu koçun hangi tip hamlesinin işe yaradığını öğrenir.

Ölçüm (takım açısından, dakika başına normalize):
- xG farkı (bizim şut xG'si − rakip şut xG'si) — koçun en doğrudan okuduğu sinyal
- xT (pas + taşıma tehdit değeri)
- şut sayısı farkı, gol farkı
- saha eğimi: hücum üçte-birindeki tamamlanmış pas payı
- defansif aksiyon payı (pres yoğunluğu vekili)

NEDEN dakika başına: 88. dakikadaki bir kararın "sonrası" penceresi 2 dakika
olabilir; ham toplamları 15 dakikalık "öncesi" ile karşılaştırmak yanıltıcıdır.
Pencereler maç sonuna/devre sınırına kırpılır, sonuç dakikaya bölünür.

Nedensellik uyarısı: bu bir VEKİL ölçümdür, kanıt değil. Skor durumu, kırmızı
kart, rakip hamlesi de aynı anda etkiler; `confidence` kısa pencerelerde ve az
olayda düşer. Hüküm bu yüzden "etkisi ölçüldü" diye sunulur, "kararın doğruydu"
diye değil.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass

from app.audit import AuditRecord, EngineResult
from app.domain import Carry, DefensiveAction, PassEvent, Shot

ENGINE_NAME = "engine.decision_impact"
ENGINE_VERSION = "1"

DEFAULT_WINDOW_MIN = 15.0
MIN_WINDOW_MIN = 3.0          # daha kısa pencere → ölçüm yapılmaz
ATTACKING_THIRD_X = 200.0 / 3  # x > 66.67 hücum üçte biri
# Hüküm eşikleri — dakika başına xG farkı değişimi
POSITIVE_XG_DELTA = 0.010     # ~15 dk'da +0.15 xG
NEGATIVE_XG_DELTA = -0.010
SUPPORT_XT_DELTA = 0.0        # ikincil onay: xT de aynı yöne gitmeli

DECISION_TYPE_LABEL: dict[str, str] = {
    "substitution": "İkame",
    "formation": "Diziliş",
    "tactical": "Taktik ayar",
    "press_height": "Pres hattı",
    "tempo": "Tempo",
    "set_piece": "Duran top",
    "man_marking": "Adam markajı",
    "time_management": "Oyun yönetimi",
    "other": "Diğer",
}

MINUTE_BANDS: tuple[tuple[str, float, float], ...] = (
    ("ilk yarı", 0.0, 45.0),
    ("46-70", 45.0, 70.0),
    ("71-85", 70.0, 85.0),
    ("86+", 85.0, 130.0),
)


@dataclass(frozen=True)
class DecisionContext:
    """Bir kararın ölçüm için gereken bağlamı (DB satırından türetilir)."""

    decision_id: int
    match_external_id: int
    team_external_id: int
    opponent_external_id: int
    minute: float
    decision_type: str
    period: int = 2
    recommended: bool | None = None


@dataclass(frozen=True)
class WindowMetrics:
    """Bir zaman penceresinin dakika-başına metrikleri."""

    minutes: float
    xg_for: float
    xg_against: float
    xg_diff: float
    xt: float
    shots_for: float
    shots_against: float
    goals_for: float
    goals_against: float
    final_third_pass_share: float   # 0..1, bizim hücum üçte-biri pas payımız
    defensive_actions: float


@dataclass(frozen=True)
class DecisionImpact:
    """Karar öncesi/sonrası ölçüm + hüküm."""

    decision_id: int
    minute: float
    decision_type: str
    decision_label: str
    pre: WindowMetrics
    post: WindowMetrics
    xg_diff_delta: float
    xt_delta: float
    shots_delta: float
    goals_delta: float
    field_tilt_delta: float
    verdict: str            # positive | negative | neutral | insufficient_data
    verdict_reason: str
    confidence: float       # 0..1 — pencere uzunluğu + olay yoğunluğu
    window_minutes: float


@dataclass(frozen=True)
class TypeStat:
    decision_type: str
    label: str
    n: int
    positive: int
    negative: int
    neutral: int
    hit_rate: float | None      # positive / (positive + negative)
    mean_xg_delta: float


@dataclass(frozen=True)
class MinuteBandStat:
    band: str
    n: int
    hit_rate: float | None
    mean_xg_delta: float


@dataclass(frozen=True)
class DecisionTrackRecord:
    """Koçun karar defteri — tip ve dakika bandı kırılımı."""

    team_external_id: int
    decisions: int
    measured: int
    positive: int
    negative: int
    neutral: int
    hit_rate: float | None
    mean_xg_delta: float
    by_type: tuple[TypeStat, ...]
    by_minute_band: tuple[MinuteBandStat, ...]
    best: DecisionImpact | None
    worst: DecisionImpact | None


def _clip_window(start: float, end: float, *, match_end: float) -> tuple[float, float]:
    lo = max(0.0, start)
    hi = min(match_end, end)
    return lo, max(lo, hi)


def _shot_xg(shot: Shot) -> float:
    from app.engine.xg import compute_shot_xg

    try:
        return compute_shot_xg(shot).value.xg
    except (ValueError, KeyError, TypeError, RuntimeError):
        return 0.0


def _window_metrics(
    *,
    lo: float,
    hi: float,
    team_id: int,
    opponent_id: int,
    passes: Sequence[PassEvent],
    carries: Sequence[Carry],
    shots: Sequence[Shot],
    defensive_actions: Sequence[DefensiveAction],
) -> WindowMetrics:
    from app.engine.xt import xt_value_at

    minutes = max(0.0, hi - lo)
    if minutes <= 0:
        return WindowMetrics(0.0, 0, 0, 0, 0, 0, 0, 0, 0, 0.0, 0)

    def _in(m: float) -> bool:
        return lo <= m < hi

    w_passes = [p for p in passes if _in(p.minute)]
    w_carries = [c for c in carries if _in(c.minute)]
    w_shots = [s for s in shots if _in(s.minute)]
    w_defs = [d for d in defensive_actions if _in(d.minute)]

    xg_for = sum(_shot_xg(s) for s in w_shots if s.team_external_id == team_id)
    xg_against = sum(_shot_xg(s) for s in w_shots if s.team_external_id == opponent_id)
    shots_for = sum(1 for s in w_shots if s.team_external_id == team_id)
    shots_against = sum(1 for s in w_shots if s.team_external_id == opponent_id)
    goals_for = sum(1 for s in w_shots if s.team_external_id == team_id and s.is_goal)
    goals_against = sum(1 for s in w_shots if s.team_external_id == opponent_id and s.is_goal)

    xt = 0.0
    for p in w_passes:
        if p.team_external_id == team_id and p.completed:
            xt += max(0.0, xt_value_at(p.end_x, p.end_y) - xt_value_at(p.start_x, p.start_y))
    for c in w_carries:
        if c.team_external_id == team_id:
            xt += max(0.0, xt_value_at(c.end_x, c.end_y) - xt_value_at(c.start_x, c.start_y))

    ours_final = sum(
        1 for p in w_passes
        if p.team_external_id == team_id and p.completed and p.end_x > ATTACKING_THIRD_X
    )
    theirs_final = sum(
        1 for p in w_passes
        if p.team_external_id == opponent_id and p.completed and p.end_x > ATTACKING_THIRD_X
    )
    tilt = ours_final / (ours_final + theirs_final) if (ours_final + theirs_final) else 0.5
    our_defs = sum(1 for d in w_defs if d.team_external_id == team_id)

    def per_min(v: float) -> float:
        return round(v / minutes, 4)

    return WindowMetrics(
        minutes=round(minutes, 2),
        xg_for=per_min(xg_for),
        xg_against=per_min(xg_against),
        xg_diff=per_min(xg_for - xg_against),
        xt=per_min(xt),
        shots_for=per_min(shots_for),
        shots_against=per_min(shots_against),
        goals_for=per_min(goals_for),
        goals_against=per_min(goals_against),
        final_third_pass_share=round(tilt, 3),
        defensive_actions=per_min(our_defs),
    )


def compute_decision_impact(
    ctx: DecisionContext,
    *,
    passes: Iterable[PassEvent],
    carries: Iterable[Carry],
    shots: Iterable[Shot],
    defensive_actions: Iterable[DefensiveAction] = (),
    window_min: float = DEFAULT_WINDOW_MIN,
    match_end_minute: float | None = None,
) -> EngineResult[DecisionImpact]:
    """Tek bir kararın öncesi/sonrası etkisi + hüküm."""
    p, c, s, d = list(passes), list(carries), list(shots), list(defensive_actions)
    last_event = max(
        [e.minute for e in p] + [e.minute for e in c] + [e.minute for e in s] + [90.0],
    )
    match_end = match_end_minute if match_end_minute is not None else last_event

    pre_lo, pre_hi = _clip_window(ctx.minute - window_min, ctx.minute, match_end=match_end)
    post_lo, post_hi = _clip_window(ctx.minute, ctx.minute + window_min, match_end=match_end)
    # Ortak argümanlar kapanışta: `**kw` sözlüğüyle geçmek değerleri karışık
    # tipe düşürüyor ve tip denetimi kayboluyordu.
    def _metrics(lo: float, hi: float) -> WindowMetrics:
        return _window_metrics(
            lo=lo, hi=hi,
            team_id=ctx.team_external_id, opponent_id=ctx.opponent_external_id,
            passes=p, carries=c, shots=s, defensive_actions=d,
        )

    pre = _metrics(pre_lo, pre_hi)
    post = _metrics(post_lo, post_hi)

    xg_delta = round(post.xg_diff - pre.xg_diff, 4)
    xt_delta = round(post.xt - pre.xt, 4)
    shots_delta = round(post.shots_for - pre.shots_for, 4)
    goals_delta = round((post.goals_for - post.goals_against) - (pre.goals_for - pre.goals_against), 4)
    tilt_delta = round(post.final_third_pass_share - pre.final_third_pass_share, 3)

    short = min(pre.minutes, post.minutes)
    events_in_windows = sum(
        1 for e in p + c + s
        if pre_lo <= e.minute < post_hi
    )
    if short < MIN_WINDOW_MIN or events_in_windows == 0:
        verdict, reason = "insufficient_data", (
            f"pencere çok kısa ({short:.1f} dk) veya olay yok — ölçüm yapılmadı"
        )
        confidence = 0.0
    else:
        if xg_delta >= POSITIVE_XG_DELTA and xt_delta >= SUPPORT_XT_DELTA:
            verdict = "positive"
            reason = f"xG farkı dk başına {xg_delta:+.3f}, xT {xt_delta:+.3f} — ikisi de lehte"
        elif xg_delta <= NEGATIVE_XG_DELTA and xt_delta <= SUPPORT_XT_DELTA:
            verdict = "negative"
            reason = f"xG farkı dk başına {xg_delta:+.3f}, xT {xt_delta:+.3f} — ikisi de aleyhte"
        else:
            verdict = "neutral"
            reason = f"xG farkı {xg_delta:+.3f}, xT {xt_delta:+.3f} — net yön yok"
        # Güven: pencere uzunluğu (yarısı tam pencere) + olay yoğunluğu
        win_conf = min(1.0, short / window_min)
        ev_conf = min(1.0, events_in_windows / 40.0)
        confidence = round(0.6 * win_conf + 0.4 * ev_conf, 2)

    impact = DecisionImpact(
        decision_id=ctx.decision_id,
        minute=ctx.minute,
        decision_type=ctx.decision_type,
        decision_label=DECISION_TYPE_LABEL.get(ctx.decision_type, ctx.decision_type),
        pre=pre, post=post,
        xg_diff_delta=xg_delta, xt_delta=xt_delta, shots_delta=shots_delta,
        goals_delta=goals_delta, field_tilt_delta=tilt_delta,
        verdict=verdict, verdict_reason=reason, confidence=confidence,
        window_minutes=window_min,
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="decision", subject_id=ctx.decision_id,
        metric="decision_impact", value=asdict(impact),
        inputs={
            "minute": ctx.minute, "window_min": window_min,
            "pre_window": [round(pre_lo, 2), round(pre_hi, 2)],
            "post_window": [round(post_lo, 2), round(post_hi, 2)],
            "events_in_windows": events_in_windows,
            "match_end_minute": round(match_end, 2),
        },
        formula=(
            "pencereler maç sonuna kırpılır, metrikler DAKİKA BAŞINA normalize edilir; "
            f"xg_diff = (bizim xG − rakip xG)/dk; positive: Δxg_diff ≥ {POSITIVE_XG_DELTA} "
            f"ve ΔxT ≥ {SUPPORT_XT_DELTA}; negative: her ikisi de ters; "
            "confidence = 0.6·(pencere/tam) + 0.4·(olay/40). Vekil ölçüm — nedensellik kanıtı değil."
        ),
    )
    return EngineResult(value=impact, audit=audit)


def compute_decision_track_record(
    team_external_id: int,
    impacts: Iterable[DecisionImpact],
) -> EngineResult[DecisionTrackRecord]:
    """Koçun karar defteri: tip ve dakika bandı kırılımlı isabet + ortalama etki."""
    items = list(impacts)
    measured = [i for i in items if i.verdict != "insufficient_data"]
    pos = [i for i in measured if i.verdict == "positive"]
    neg = [i for i in measured if i.verdict == "negative"]
    neu = [i for i in measured if i.verdict == "neutral"]

    def _hit(p: int, n: int) -> float | None:
        return round(p / (p + n), 3) if (p + n) else None

    def _mean_xg(xs: list[DecisionImpact]) -> float:
        return round(sum(i.xg_diff_delta for i in xs) / len(xs), 4) if xs else 0.0

    by_type: list[TypeStat] = []
    for dtype in sorted({i.decision_type for i in measured}):
        group = [i for i in measured if i.decision_type == dtype]
        gp = sum(1 for i in group if i.verdict == "positive")
        gn = sum(1 for i in group if i.verdict == "negative")
        by_type.append(TypeStat(
            decision_type=dtype,
            label=DECISION_TYPE_LABEL.get(dtype, dtype),
            n=len(group), positive=gp, negative=gn,
            neutral=len(group) - gp - gn,
            hit_rate=_hit(gp, gn), mean_xg_delta=_mean_xg(group),
        ))

    bands: list[MinuteBandStat] = []
    for label, lo, hi in MINUTE_BANDS:
        group = [i for i in measured if lo <= i.minute < hi]
        if not group:
            continue
        gp = sum(1 for i in group if i.verdict == "positive")
        gn = sum(1 for i in group if i.verdict == "negative")
        bands.append(MinuteBandStat(
            band=label, n=len(group), hit_rate=_hit(gp, gn), mean_xg_delta=_mean_xg(group),
        ))

    record = DecisionTrackRecord(
        team_external_id=team_external_id,
        decisions=len(items), measured=len(measured),
        positive=len(pos), negative=len(neg), neutral=len(neu),
        hit_rate=_hit(len(pos), len(neg)), mean_xg_delta=_mean_xg(measured),
        by_type=tuple(by_type), by_minute_band=tuple(bands),
        best=max(measured, key=lambda i: i.xg_diff_delta) if measured else None,
        worst=min(measured, key=lambda i: i.xg_diff_delta) if measured else None,
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="team", subject_id=team_external_id,
        metric="decision_track_record", value=asdict(record),
        inputs={"decisions": len(items), "measured": len(measured)},
        formula=(
            "hit_rate = positive / (positive + negative); ölçülemeyen kararlar "
            "(kısa pencere / olay yok) paydaya girmez; mean_xg_delta ölçülenlerin ortalaması"
        ),
    )
    return EngineResult(value=record, audit=audit)
