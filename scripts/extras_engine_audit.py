"""İkinci grup motor audit (Faz 5 #46).

`scripts/full_season_audit.py` 22 team-level motoru La Liga 2018/19
StatsBomb Open datası üzerinde audit'liyor (PPDA, defensive_line, vb).
Bu script aynı patterni **ikinci grup** motora yayar — pre-match
analytics ve agent benzeri motorlar.

Hedef: hangi engine "STRONG_SIGNAL" verdi (CV ≥ 0.3, n_samples ≥ 20),
hangisi "NOISE" (gürültü). Pilot kulüpe götürülecek motor seçimi
audit sonucuna göre yapılır.

Çalıştırma:
    DATABASE_URL="sqlite:///full_season.db" \\
        python -m scripts.extras_engine_audit

NOT: Bu script `full_season_audit` ingest job'undan SONRA çalışmalı —
DB'de events + appearances dolu olmalı. Boş DB'de "no data" mesajı
döner; audit yapmaz.

Çıktı:
    extras_engine_audit.json — engine başına {n_samples, mean, stdev,
                                              cv, verdict}
    extras_engine_audit.md   — okunabilir özet
"""

from __future__ import annotations

import json
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from sqlalchemy import select

from app.core.logging import get_logger
from app.db import models
from app.db.base import Base
from app.db.session import SessionLocal
from app.db.session import engine as db_engine
from app.sports import football

log = get_logger(__name__)

OUTPUT_JSON = Path("extras_engine_audit.json")
OUTPUT_MD = Path("extras_engine_audit.md")

# Audit eşikleri (full_season_audit ile aynı)
CV_STRONG = 0.30  # signal-to-noise eşiği
N_MIN_RELIABLE = 20  # min sample size


@dataclass(frozen=True)
class EngineSpec:
    """İkinci grup audit girişi.

    `extractor(session) -> list[float]` — engine'i çağırıp tek bir metric
    skaler değerini bir popülasyon (takım/oyuncu) için döker. Boş liste =
    veri yok (skip).
    """

    name: str
    metric: str
    lower_is_better: bool
    extractor: Callable[[Any], list[float]]
    notes: str = ""


# --------------------------------------------------------------------------- #
# Engine extractor'ları — minimal, DB'den okuyup tek metric döker
# --------------------------------------------------------------------------- #


def _all_teams(session) -> list[int]:
    rows = session.execute(
        select(models.Team.external_id).where(
            models.Team.sport == football.SPORT_NAME,
        )
    ).scalars().all()
    return list(rows)


def _all_player_ids(session) -> list[int]:
    rows = session.execute(
        select(models.PlayerAppearance.player_external_id)
        .where(models.PlayerAppearance.sport == football.SPORT_NAME)
        .distinct()
    ).scalars().all()
    return [int(r) for r in rows]


def _team_match_list(session, team_id: int) -> list[Any]:
    from sqlalchemy import or_
    return list(session.execute(
        select(models.Match).where(
            models.Match.sport == football.SPORT_NAME,
            or_(
                models.Match.home_team_external_id == team_id,
                models.Match.away_team_external_id == team_id,
            ),
        )
    ).scalars())


# Engine extractors — her biri popülasyon için metric vector çıkarır
def ext_form_ppg(session) -> list[float]:
    from app.engine.form import compute_form
    out: list[float] = []
    for tid in _all_teams(session):
        matches = _team_match_list(session, tid)
        if len(matches) < 3:
            continue
        try:
            r = compute_form(tid, matches, last_n=5).value
        except (ValueError, ZeroDivisionError):
            continue
        out.append(r.points_per_game)
    return out


def ext_rating_overall(session) -> list[float]:
    from app.engine.rating import compute_team_rating
    out: list[float] = []
    for tid in _all_teams(session):
        matches = _team_match_list(session, tid)
        if len(matches) < 3:
            continue
        try:
            r = compute_team_rating(tid, matches, last_n=10).value
        except (ValueError, ZeroDivisionError):
            continue
        out.append(r.rating)
    return out


def ext_load_minutes_per_week(session) -> list[float]:
    from app.engine.load import compute_player_load
    out: list[float] = []
    for pid in _all_player_ids(session):
        apps = list(session.execute(
            select(models.PlayerAppearance).where(
                models.PlayerAppearance.sport == football.SPORT_NAME,
                models.PlayerAppearance.player_external_id == pid,
            )
        ).scalars())
        if not apps:
            continue
        try:
            r = compute_player_load(pid, apps, window_days=14).value
        except (ValueError, ZeroDivisionError):
            continue
        out.append(r.minutes_per_week)
    return out


def ext_injury_risk_score(session) -> list[float]:
    from app.engine.injury_risk import compute_injury_risk
    from app.engine.load import compute_player_load
    out: list[float] = []
    for pid in _all_player_ids(session):
        apps = list(session.execute(
            select(models.PlayerAppearance).where(
                models.PlayerAppearance.sport == football.SPORT_NAME,
                models.PlayerAppearance.player_external_id == pid,
            )
        ).scalars())
        if not apps:
            continue
        try:
            load_r = compute_player_load(pid, apps, window_days=14).value
            risk_r = compute_injury_risk(
                pid,
                minutes_per_week=load_r.minutes_per_week,
                back_to_back_count=load_r.back_to_back_count,
            ).value
        except (ValueError, ZeroDivisionError):
            continue
        out.append(risk_r.risk_score)
    return out


def ext_xa_per_match(session) -> list[float]:
    """xA — pas-tabanlı, her takım için per-match ortalaması."""
    from app.data.loaders import load_team_events
    from app.engine.xa import compute_team_xa
    out: list[float] = []
    for tid in _all_teams(session):
        loaded = load_team_events(session, tid, last_n=10)
        if loaded.total == 0:
            continue
        try:
            r = compute_team_xa(tid, loaded.passes).value
        except (ValueError, ZeroDivisionError, TypeError):
            continue
        n = max(1, len(loaded.match_ids))
        out.append(getattr(r, "total_xa", 0.0) / n)
    return out


def ext_progressive_passes(session) -> list[float]:
    from app.data.loaders import load_team_events
    from app.engine.progressive_passes import compute_progressive_passes
    out: list[float] = []
    for tid in _all_teams(session):
        loaded = load_team_events(session, tid, last_n=10)
        if loaded.total == 0:
            continue
        try:
            r = compute_progressive_passes(tid, loaded.passes).value
        except (ValueError, ZeroDivisionError, TypeError):
            continue
        out.append(float(getattr(r, "total_progressive", 0)))
    return out


def ext_carries_into_third(session) -> list[float]:
    from app.data.loaders import load_team_events
    from app.engine.carries_into_final_third import (
        compute_carries_into_final_third,
    )
    out: list[float] = []
    for tid in _all_teams(session):
        loaded = load_team_events(session, tid, last_n=10)
        if loaded.total == 0:
            continue
        try:
            r = compute_carries_into_final_third(tid, loaded.carries).value
        except (ValueError, ZeroDivisionError, TypeError):
            continue
        out.append(float(getattr(r, "total_carries_into_final_third", 0)))
    return out


def ext_off_ball_runs(session) -> list[float]:
    from app.data.loaders import load_team_events
    from app.engine.off_ball_runs import compute_off_ball_runs
    out: list[float] = []
    for tid in _all_teams(session):
        loaded = load_team_events(session, tid, last_n=10)
        if loaded.total == 0:
            continue
        try:
            r = compute_off_ball_runs(
                tid, loaded.passes, loaded.carries,
            ).value
        except (ValueError, ZeroDivisionError, TypeError):
            continue
        out.append(float(getattr(r, "total_runs", 0)))
    return out


def ext_overperformance_xg_diff(session) -> list[float]:
    """xG vs gerçek goller — overperformance göstergesi."""
    from app.data.loaders import load_team_events, shots_by_team
    from app.engine.overperformance import compute_overperformance
    out: list[float] = []
    for tid in _all_teams(session):
        loaded = load_team_events(session, tid, last_n=10)
        if loaded.total == 0:
            continue
        try:
            shots = shots_by_team(loaded.shots, tid)
            r = compute_overperformance(tid, shots).value
        except (ValueError, ZeroDivisionError, TypeError):
            continue
        diff = getattr(r, "goals_minus_xg", None)
        if diff is None:
            continue
        out.append(float(diff))
    return out


# Audit edilecek motor listesi — ilk grupta olmayan, anlamlı extractable.
# Yeni motor eklemek: extractor fonksiyon yaz + bu listeye satır ekle.
EXTRAS_ENGINES: list[EngineSpec] = [
    EngineSpec("form", "points_per_game", False, ext_form_ppg,
               "Pre-match form — takım PPG"),
    EngineSpec("rating", "rating", False, ext_rating_overall,
               "Pre-match rating — overall composite"),
    EngineSpec("load", "minutes_per_week", False, ext_load_minutes_per_week,
               "Player load — 14 günlük dakika/hafta"),
    EngineSpec("injury_risk", "risk_score", True, ext_injury_risk_score,
               "Injury risk — Gabbett heuristic, 0-100"),
    EngineSpec("xa", "xa_per_match", False, ext_xa_per_match,
               "Expected assists per match"),
    EngineSpec("progressive_passes", "total_progressive",
               False, ext_progressive_passes,
               "Progressive passes (forward 30y+)"),
    EngineSpec("carries_into_final_third",
               "total_carries_into_final_third",
               False, ext_carries_into_third,
               "Final third'a top kazanma"),
    EngineSpec("off_ball_runs", "total_runs", False, ext_off_ball_runs,
               "Off-ball run pattern density"),
    EngineSpec("overperformance", "goals_minus_xg",
               False, ext_overperformance_xg_diff,
               "xG vs actual goal differential — finishing quality"),
]


# --------------------------------------------------------------------------- #
# Audit pipeline — mean / stdev / CV / verdict
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class AuditEntry:
    engine: str
    metric: str
    n_samples: int
    mean: float
    stdev: float
    cv: float
    spread: float
    verdict: str
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "engine": self.engine,
            "metric": self.metric,
            "n_samples": self.n_samples,
            "mean": round(self.mean, 4),
            "stdev": round(self.stdev, 4),
            "cv": round(self.cv, 4),
            "spread": round(self.spread, 4),
            "verdict": self.verdict,
            "notes": self.notes,
        }


def _verdict(n: int, cv: float) -> str:
    if n < N_MIN_RELIABLE:
        return "INSUFFICIENT_DATA"
    if cv >= CV_STRONG:
        return "STRONG_SIGNAL"
    if cv >= 0.10:
        return "WEAK_SIGNAL"
    return "NOISE"


def _audit_spec(session, spec: EngineSpec) -> AuditEntry:
    samples = spec.extractor(session)
    n = len(samples)
    if n < 2:
        return AuditEntry(
            engine=spec.name, metric=spec.metric,
            n_samples=n, mean=0.0, stdev=0.0, cv=0.0, spread=0.0,
            verdict="INSUFFICIENT_DATA", notes=spec.notes,
        )
    mean = statistics.mean(samples)
    stdev = statistics.stdev(samples) if n > 1 else 0.0
    cv = abs(stdev / mean) if mean else 0.0
    spread = max(samples) - min(samples)
    return AuditEntry(
        engine=spec.name, metric=spec.metric, n_samples=n,
        mean=mean, stdev=stdev, cv=cv, spread=spread,
        verdict=_verdict(n, cv), notes=spec.notes,
    )


def run_audit() -> list[AuditEntry]:
    Base.metadata.create_all(db_engine)
    entries: list[AuditEntry] = []
    with SessionLocal() as session:
        sample_count = session.execute(
            select(models.Match).where(
                models.Match.sport == football.SPORT_NAME,
            ).limit(1)
        ).scalar_one_or_none()
        if sample_count is None:
            log.warning("DB'de hiç maç yok — full_season_audit.py önce çalışmalı")
            return []
        for spec in EXTRAS_ENGINES:
            log.info("auditing %s …", spec.name)
            entry = _audit_spec(session, spec)
            entries.append(entry)
            log.info(
                "  %s: n=%d cv=%.3f verdict=%s",
                spec.name, entry.n_samples, entry.cv, entry.verdict,
            )
    return entries


def _format_markdown(entries: list[AuditEntry]) -> str:
    lines = [
        "# Extras Engine Audit (Faz 5 #46)",
        "",
        f"İkinci grup {len(entries)} motor; eşikler: CV ≥ {CV_STRONG} → "
        f"STRONG; n ≥ {N_MIN_RELIABLE} reliable.",
        "",
        "| Engine | Metric | n | mean | cv | verdict |",
        "|---|---|---|---|---|---|",
    ]
    for e in entries:
        verdict_emoji = {
            "STRONG_SIGNAL": "🟢",
            "WEAK_SIGNAL": "🟡",
            "NOISE": "🔴",
            "INSUFFICIENT_DATA": "⚪",
        }.get(e.verdict, "")
        lines.append(
            f"| `{e.engine}` | {e.metric} | {e.n_samples} | "
            f"{e.mean:.3f} | {e.cv:.3f} | {verdict_emoji} {e.verdict} |"
        )
    lines.append("")
    lines.append("Notes: bkz. JSON + audit-pipeline `_verdict()` kuralları.")
    return "\n".join(lines)


def main() -> int:
    entries = run_audit()
    if not entries:
        log.warning("audit boş — script çıkıyor")
        return 1
    OUTPUT_JSON.write_text(
        json.dumps(
            {"audit": [e.to_dict() for e in entries]},
            indent=2, ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    OUTPUT_MD.write_text(_format_markdown(entries), encoding="utf-8")
    log.info(
        "audit yazıldı: %s + %s (%d engine)",
        OUTPUT_JSON, OUTPUT_MD, len(entries),
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
