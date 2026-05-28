"""VAEP v2 — tabular ML training from events table.

Heuristic baseline (xT grid'i) yerine takımın kendi event'lerinden öğrenilen
**tabular value function**. Klassik Markov benzeri:

Algoritma:
1. Events tablosundan tüm pass + carry'leri zone-bin'e indir
   (zone = (x_bin, y_bin); x_bin=0..3, y_bin=0..2 → 12 zone)
2. Her event için ileri-bakış (next K events same match) içinde:
   - Aynı takım gol attı mı (label_score)
   - Rakip gol attı mı (label_concede)
3. Her zone için empirik P(score) ve P(concede) hesapla
4. Sonuçları cache_entries'e yaz (source=vaep_model, key=tabular_v1)

Inference (compute.py içinden):
- Cache varsa: ΔV(action) = (P(score|end) - P(score|start))
  - (P(concede|end) - P(concede|start))
- Yoksa: heuristic baseline (1-baseline) kullan

Pure-Python (sklearn yok). Multi-tenant aware.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.cache.store import cache_set
from app.db import models
from app.sports import football

CACHE_SOURCE = "vaep_model"
CACHE_KEY = "tabular_v1"

# Zone grid: 4 (x) × 3 (y) = 12 zone
ZONE_X_BINS = 4
ZONE_Y_BINS = 3

# İleri bakış penceresi (event sayısı)
LOOKAHEAD_EVENTS = 10


def _zone_id(x: float, y: float) -> int:
    """0..11 — (x_bin, y_bin) → flat index."""
    xb = min(int(x / (100.0 / ZONE_X_BINS)), ZONE_X_BINS - 1)
    yb = min(int(y / (100.0 / ZONE_Y_BINS)), ZONE_Y_BINS - 1)
    return xb * ZONE_Y_BINS + yb


@dataclass(frozen=True)
class VAEPTrainingReport:
    sample_count: int
    matches_used: int
    zones: int
    score_lookup: dict[str, float]    # str(zone_id) → P(score)
    concede_lookup: dict[str, float]
    cache_written: bool


class NotEnoughTrainingData(Exception):
    """Train için yeterli event yok."""


def _label_events_in_match(
    rows: list[models.EventRow], lookahead: int = LOOKAHEAD_EVENTS,
) -> list[tuple[int, int, int]]:
    """Her event'e (zone_id, label_score, label_concede) etiketi.

    Sıralı (match içinde minute artan); next K event'te aynı takım/farklı
    takım gol attı mı bak.
    """
    labelled: list[tuple[int, int, int]] = []
    for i, ev in enumerate(rows):
        # Sadece pas/carry için inference yapacağız (şut zaten gol bilgisi taşıyor)
        if ev.event_type not in ("pass", "carry"):
            continue
        if ev.start_x is None or ev.start_y is None:
            continue
        zid = _zone_id(ev.start_x, ev.start_y)

        label_score = 0
        label_concede = 0
        own_team = ev.team_external_id
        # Sonraki K event'e bak
        for j in range(i + 1, min(i + 1 + lookahead, len(rows))):
            future = rows[j]
            if future.event_type != "shot" or not future.is_goal:
                continue
            # Şut atan oyuncunun takımı bizim mi rakibin mi?
            # Shot EventRow'da team_external_id None — pas/carry team'i ile
            # eşleştirmek için minute-window heuristic
            # Yaklaşım: aynı possession_id varsa, possession'ın takımı
            shooting_team = future.team_external_id
            if shooting_team is None and future.possession_id is not None:
                # En yakın aynı possession_id'li pass/carry'den takımı bul
                for back in range(j - 1, max(j - 5, -1), -1):
                    if rows[back].possession_id == future.possession_id and rows[back].team_external_id is not None:
                        shooting_team = rows[back].team_external_id
                        break
            if shooting_team == own_team:
                label_score = 1
            elif shooting_team is not None:
                label_concede = 1
            # İlk gol yeter
            if label_score or label_concede:
                break
        labelled.append((zid, label_score, label_concede))
    return labelled


def train_vaep_model(
    session: Session,
    *,
    tenant_id: str,
    min_samples: int = 100,
    lookahead: int = LOOKAHEAD_EVENTS,
    write_cache: bool = True,
) -> VAEPTrainingReport:
    """Events tablosundan tabular VAEP modeli train et + cache'e yaz.

    `min_samples=100` default eşiği — küçük data'da overfit'ten kaçınmak için.
    """
    # Tüm event'leri match + minute sıralı çek
    rows = list(session.execute(
        select(models.EventRow).where(
            models.EventRow.sport == football.SPORT_NAME,
            models.EventRow.tenant_id == tenant_id,
        ).order_by(
            models.EventRow.match_external_id,
            models.EventRow.period, models.EventRow.minute,
        )
    ).scalars())

    if len(rows) < min_samples:
        raise NotEnoughTrainingData(
            f"events sample {len(rows)} < min {min_samples}; "
            f"daha fazla maç ingest et"
        )

    # Match'lere böl
    matches: dict[int, list[models.EventRow]] = {}
    for r in rows:
        matches.setdefault(r.match_external_id, []).append(r)

    all_labelled: list[tuple[int, int, int]] = []
    for _mid, m_rows in matches.items():
        all_labelled.extend(_label_events_in_match(m_rows, lookahead=lookahead))

    if len(all_labelled) < min_samples:
        raise NotEnoughTrainingData(
            f"label edilebilir event {len(all_labelled)} < min {min_samples}"
        )

    # Empirik probabilite — her zone için
    zone_stats: dict[int, list[int]] = {
        z: [0, 0, 0] for z in range(ZONE_X_BINS * ZONE_Y_BINS)
    }  # [count, score_sum, concede_sum]
    for zid, ls, lc in all_labelled:
        zone_stats[zid][0] += 1
        zone_stats[zid][1] += ls
        zone_stats[zid][2] += lc

    # Laplace smoothing (count + 1, num + 0.01 to avoid zero P)
    score_lookup: dict[str, float] = {}
    concede_lookup: dict[str, float] = {}
    for zid, (n, s, c) in zone_stats.items():
        if n == 0:
            score_lookup[str(zid)] = 0.0
            concede_lookup[str(zid)] = 0.0
        else:
            score_lookup[str(zid)] = round((s + 0.01) / (n + 1), 5)
            concede_lookup[str(zid)] = round((c + 0.01) / (n + 1), 5)

    report = VAEPTrainingReport(
        sample_count=len(all_labelled),
        matches_used=len(matches),
        zones=ZONE_X_BINS * ZONE_Y_BINS,
        score_lookup=score_lookup,
        concede_lookup=concede_lookup,
        cache_written=False,
    )

    if write_cache:
        from datetime import UTC, datetime
        payload: dict[str, Any] = {
            "score_lookup": score_lookup,
            "concede_lookup": concede_lookup,
            "sample_count": len(all_labelled),
            "matches_used": len(matches),
            "trained_at": datetime.now(UTC).isoformat(),
            "lookahead_events": lookahead,
            "zone_x_bins": ZONE_X_BINS,
            "zone_y_bins": ZONE_Y_BINS,
        }
        cache_set(
            session,
            source=CACHE_SOURCE, key=CACHE_KEY,
            value=payload, ttl_seconds=7 * 24 * 3600,
        )
        report = VAEPTrainingReport(
            sample_count=report.sample_count,
            matches_used=report.matches_used,
            zones=report.zones,
            score_lookup=report.score_lookup,
            concede_lookup=report.concede_lookup,
            cache_written=True,
        )
    return report
