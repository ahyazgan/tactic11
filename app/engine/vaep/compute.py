"""VAEP — Possession Value framework (KU Leuven Decroos et al. 2019).

Akademik VAEP iki ML modeli eğitir:
- P_score(state): bu state'ten X aksiyon içinde gol atma olasılığı
- P_concede(state): bu state'ten X aksiyon içinde gol yeme olasılığı
- ΔV(action) = (P_score(after) − P_score(before)) − (P_concede(after) − P_concede(before))

Bu modül pure-Python **HEURISTIC BASELINE**'ı sağlar — sklearn/numpy gerekmez.
Heuristic value fonksiyonu xT 12×8 grid değerini kullanır (engine.xt). Gerçek
ML modeli (predict_ml gibi train job ile) sonra plug edilebilir; arayüz aynı.

Pas/carry/şut başına value hesaplanır, oyuncu/takım için 90 dakikaya
normalize edilir. Bu, "yapan oyuncunun her bir top temasının ne kadar gol
tehdidi yarattığı" sayısı.

Audit'li, multi-tenant safe, pure-compute.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.audit import AuditRecord, EngineResult
from app.domain import Carry, PassEvent, Shot
from app.engine.xt import xt_value_at

ENGINE_NAME = "engine.vaep"
ENGINE_VERSION = "1-baseline"  # _baseline = heuristic; v2 = ML-trained

# Heuristic baseline:
# - Pas/carry value = ΔxT (xT(end) − xT(start)); negatif olabilir (geri pas)
# - Şut value = xG (Shot domain'inde yok → geometric proxy: 1 − distance/100)
# - Tamamlanmamış pas: V_score = ΔxT × 0.5 (yarı katkı, risk cezası);
#   V_concede = 0.30 × xT(start) (rakibe verdiğin başlangıç tehdidi)
# Ayar parametreleri:
INCOMPLETE_PASS_SCORE_PENALTY = 0.5
INCOMPLETE_PASS_CONCEDE_RATIO = 0.30
SHOT_DEFAULT_XG_PROXY = 0.10   # rough; engine.xg.geometric daha sofistike


def _shot_xg_proxy(s: Shot) -> float:
    """Geometric proxy: kale uzaklığı + açı.

    Gerçek: app.engine.xg.compute_shot_xg_geometric. Burada inline basitleştirme.
    Kale (100, 50). Distance normalize 0-100 saha üstünde.
    """
    dx = 100.0 - s.x
    dy = 50.0 - s.y
    dist = (dx * dx + dy * dy) ** 0.5
    # Kale ağzına yakın → yüksek xG
    if dist <= 5.0:
        return 0.55
    if dist <= 12.0:
        return 0.25
    if dist <= 20.0:
        return 0.10
    if dist <= 30.0:
        return 0.04
    return 0.01


def _pass_value(p: PassEvent) -> tuple[float, float]:
    """(score_value, concede_value) — pas için.

    Heuristic:
    - Tamamlanmış: ΔxT (full); concede=0 (rakipte değil)
    - Tamamlanmamış: ΔxT × 0.5 (yarı kredit); concede = xT(start) × 0.30
    """
    xt_start = xt_value_at(p.start_x, p.start_y)
    xt_end = xt_value_at(p.end_x, p.end_y)
    delta = xt_end - xt_start
    if p.completed:
        return delta, 0.0
    return delta * INCOMPLETE_PASS_SCORE_PENALTY, xt_start * INCOMPLETE_PASS_CONCEDE_RATIO


def _carry_value(c: Carry) -> float:
    """Carry tamamı tamamlanmış kabul (oyuncu topla mesafe aldı)."""
    return xt_value_at(c.end_x, c.end_y) - xt_value_at(c.start_x, c.start_y)


def _shot_value(s: Shot) -> tuple[float, float]:
    """Şut → xG. Concede=0 (gol kaçırma rakibe top kaybı değil; possession bitti)."""
    return _shot_xg_proxy(s), 0.0


@dataclass(frozen=True)
class VAEPReport:
    player_external_id: int | None
    team_external_id: int | None
    matches_analyzed: int
    minutes_played: float | None
    total_actions: int
    sum_score_value: float          # gol-tehdidi toplam katkısı
    sum_concede_value: float        # gol-yedirme toplam katkısı
    vaep_value: float               # score − concede (toplam)
    vaep_per_90: float | None
    score_per_90: float | None
    concede_per_90: float | None
    model_version: str              # "1-baseline" şu an, "2-ml" sonra
    by_action: dict[str, float]     # tipe göre breakdown


def compute_vaep(
    *,
    team_external_id: int | None = None,
    player_external_id: int | None = None,
    all_passes: Iterable[PassEvent],
    all_carries: Iterable[Carry],
    all_shots: Iterable[Shot],
    minutes_played: float | None = None,
    matches_analyzed: int = 1,
) -> EngineResult[VAEPReport]:
    """Bir takım VEYA oyuncu için VAEP toplam değeri.

    Heuristic baseline (model_version="1-baseline"); v2'de ML.
    Tüm pas + carry + şutu döner; subject filtre yapar.
    """
    if team_external_id is None and player_external_id is None:
        raise ValueError("team_external_id veya player_external_id verilmeli")

    def _matches_pass(p: PassEvent) -> bool:
        if player_external_id is not None:
            return p.player_external_id == player_external_id
        return p.team_external_id == team_external_id

    def _matches_carry(c: Carry) -> bool:
        if player_external_id is not None:
            return c.player_external_id == player_external_id
        return c.team_external_id == team_external_id

    def _matches_shot(s: Shot) -> bool:
        # Shot domain'inde team_id yok; sadece player_id ile filtre
        if player_external_id is not None:
            return s.player_external_id == player_external_id
        return True  # team-level: caller önceden filtre etmedi → tüm şut

    passes = [p for p in all_passes if _matches_pass(p)]
    carries = [c for c in all_carries if _matches_carry(c)]
    shots = [s for s in all_shots if _matches_shot(s)]

    sum_score = 0.0
    sum_concede = 0.0
    pass_total = 0.0
    carry_total = 0.0
    shot_total = 0.0

    for p in passes:
        sv, cv = _pass_value(p)
        sum_score += sv
        sum_concede += cv
        pass_total += sv - cv
    for c in carries:
        v = _carry_value(c)
        sum_score += v
        carry_total += v
    for s in shots:
        sv, cv = _shot_value(s)
        sum_score += sv
        sum_concede += cv
        shot_total += sv - cv

    total = len(passes) + len(carries) + len(shots)
    vaep = sum_score - sum_concede
    per_90: float | None = None
    score_per_90: float | None = None
    concede_per_90: float | None = None
    if minutes_played and minutes_played > 0:
        per_90 = round(vaep / minutes_played * 90, 3)
        score_per_90 = round(sum_score / minutes_played * 90, 3)
        concede_per_90 = round(sum_concede / minutes_played * 90, 3)

    report = VAEPReport(
        player_external_id=player_external_id,
        team_external_id=team_external_id,
        matches_analyzed=matches_analyzed,
        minutes_played=minutes_played,
        total_actions=total,
        sum_score_value=round(sum_score, 4),
        sum_concede_value=round(sum_concede, 4),
        vaep_value=round(vaep, 4),
        vaep_per_90=per_90,
        score_per_90=score_per_90,
        concede_per_90=concede_per_90,
        model_version=ENGINE_VERSION,
        by_action={
            "passes": round(pass_total, 4),
            "carries": round(carry_total, 4),
            "shots": round(shot_total, 4),
        },
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="player" if player_external_id else "team",
        subject_id=player_external_id or team_external_id or 0,
        metric="vaep",
        value={
            "vaep_value": report.vaep_value,
            "vaep_per_90": per_90,
            "model_version": ENGINE_VERSION,
            "total_actions": total,
        },
        inputs={
            "incomplete_pass_score_penalty": INCOMPLETE_PASS_SCORE_PENALTY,
            "incomplete_pass_concede_ratio": INCOMPLETE_PASS_CONCEDE_RATIO,
            "matches_analyzed": matches_analyzed,
            "model_type": "heuristic_baseline_xt_grid",
        },
        formula=(
            "VAEP = Σ ΔP(score) − Σ ΔP(concede); "
            "baseline: pas/carry = ΔxT, şut = geometric xG proxy, "
            "incomplete pass = ΔxT × 0.5 score + 0.30 × xT(start) concede. "
            "v2: gerçek ML modeli (KU Leuven Decroos 2019)."
        ),
    )
    return EngineResult(value=report, audit=audit)
