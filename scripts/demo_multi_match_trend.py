"""Multi-match real demo: 5 Barcelona maçı ingest + trend analizi.

La Liga 2018/19'dan Barcelona'nın 5 maçını indirir, events tablosuna yazar,
sonra tactical_trend engine'iyle PPDA/tilt/xT/possession/dominance trend
çıkarır.

Sezon-boyu intelligence platformunun "ürünleştirilmiş" demosu.

Kullanım:
    DATABASE_URL="sqlite:///demo_multi.db" python -m scripts.demo_multi_match_trend
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.core.logging import get_logger
from app.data.ingest.event import ingest_events_for_match
from app.data.loaders import load_match_events
from app.data.sources.statsbomb_open import StatsBombOpen
from app.db import models
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.engine.field_tilt import compute_field_tilt
from app.engine.match_dominance import compute_match_dominance
from app.engine.ppda import compute_ppda
from app.engine.tactical_trend import compute_tactical_trend
from app.engine.xt import compute_team_xt
from app.sports import football
from scripts.demo_real_statsbomb import _seed_match_from_statsbomb

log = get_logger(__name__)

BARCA_TEAM_ID = 217
TENANT_ID = "t-demo"

# La Liga 2018/19 Barcelona match'leri (StatsBomb match_id'leri)
# Sample 5 maç — sezonun farklı dönemlerinden
BARCA_MATCHES = [
    15998,  # Leganés 2-1 Barca
    15978,  # Sociedad 1-2 Barca
    16029,  # Barca 4-2 Sevilla
    16086,  # Barca 4-1 Sevilla?
    16195,  # Barca's later match
]


def ensure_match_ids() -> list[int]:
    """StatsBomb'dan Barca match'lerini dinamik bul (yukarıdaki listede
    olmayan match_id'ler için)."""
    src = StatsBombOpen()
    all_matches = src.get_matches(competition_id=11, season_id=4)
    barca = [
        m for m in all_matches
        if m["home_team"]["home_team_id"] == BARCA_TEAM_ID
        or m["away_team"]["away_team_id"] == BARCA_TEAM_ID
    ]
    # İlk 5 (kronolojik artan)
    barca.sort(key=lambda m: m["match_date"])
    return [m["match_id"] for m in barca[:5]]


def run_demo() -> dict:
    Base.metadata.create_all(engine)
    src = StatsBombOpen()
    match_ids = ensure_match_ids()

    print(f"\n{'='*70}")
    print("  Multi-Match Real Demo — Barcelona La Liga 2018/19 (5 maç)")
    print(f"  Tenant: {TENANT_ID} · Team: {BARCA_TEAM_ID}")
    print(f"{'='*70}\n")
    print(f"İşlenecek match_id'ler: {match_ids}\n")

    with SessionLocal() as session:
        session.info["tenant_id"] = TENANT_ID

        # 1. Ingest 5 maç
        print("[1/3] 5 maçı ingest et...")
        for mid in match_ids:
            try:
                _seed_match_from_statsbomb(
                    session, match_id=mid, tenant_id=TENANT_ID,
                )
                session.commit()
                report = ingest_events_for_match(
                    session, src, match_external_id=mid, tenant_id=TENANT_ID,
                )
                session.commit()
                print(f"    match {mid}: {report.rows_inserted} event inserted")
            except Exception as e:
                print(f"    match {mid}: FAIL ({str(e)[:80]})")

        # 2. Trend hesabı (manuel — endpoint pattern'i kopya)
        print("\n[2/3] 5-maç trend hesabı...")
        match_rows = list(session.execute(
            select(models.Match).where(
                models.Match.sport == football.SPORT_NAME,
                (models.Match.home_team_external_id == BARCA_TEAM_ID)
                | (models.Match.away_team_external_id == BARCA_TEAM_ID),
                models.Match.status.in_(football.FINISHED_STATUSES),
            ).order_by(models.Match.kickoff)
        ).scalars())
        print(f"    FINISHED maç sayısı: {len(match_rows)}")

        series: dict[str, list[float]] = {
            "ppda": [], "field_tilt": [], "team_xt": [],
            "possession_share": [], "dominance_score": [],
        }
        match_summary: list[dict[str, Any]] = []
        for m in match_rows:
            loaded = load_match_events(session, m.external_id)
            if loaded.total == 0:
                continue
            opp_id = (
                m.away_team_external_id if m.home_team_external_id == BARCA_TEAM_ID
                else m.home_team_external_id
            )
            ppda = compute_ppda(BARCA_TEAM_ID, loaded.passes,
                                loaded.defensive_actions).value
            tilt = compute_field_tilt(BARCA_TEAM_ID, opp_id, loaded.passes).value
            xt = compute_team_xt(BARCA_TEAM_ID, loaded.passes, loaded.carries).value
            team_pass = sum(1 for p in loaded.passes if p.team_external_id == BARCA_TEAM_ID)
            opp_pass = sum(1 for p in loaded.passes if p.team_external_id == opp_id)
            poss = team_pass / (team_pass + opp_pass) if (team_pass + opp_pass) else 0.5
            dom = compute_match_dominance(
                team_external_id=BARCA_TEAM_ID, opponent_team_external_id=opp_id,
                team_shots=loaded.shots, opponent_shots=loaded.shots,
                all_passes=loaded.passes, team_carries=loaded.carries,
                opponent_carries=loaded.carries,
            ).value
            series["ppda"].append(ppda.ppda)
            series["field_tilt"].append(tilt.team_a_tilt)
            series["team_xt"].append(xt.total_xt)
            series["possession_share"].append(round(poss, 3))
            series["dominance_score"].append(dom.dominance_score)
            match_summary.append({
                "match_id": m.external_id,
                "kickoff": m.kickoff.isoformat() if m.kickoff else None,
                "score": f"{m.home_score}-{m.away_score}",
                "opp_id": opp_id,
            })

        higher_better = {
            "ppda": False, "field_tilt": True, "team_xt": True,
            "possession_share": True, "dominance_score": True,
        }
        trends = {}
        for metric, vals in series.items():
            t = compute_tactical_trend(
                metric, vals, higher_is_better=higher_better[metric],
                subject_id=BARCA_TEAM_ID,
            ).value
            trends[metric] = {
                "series": list(t.series),
                "mean": t.mean,
                "slope": t.slope,
                "direction": t.direction,
                "biggest_shift": t.biggest_match_to_match_shift,
                "biggest_shift_match_idx": t.biggest_shift_match_idx,
            }

        # 3. Print summary
        print("\n[3/3] Sezon trend özet (Barca son 5 maç):")
        for metric, tr in trends.items():
            print(f"  {metric:20s} dir={tr['direction']:12s} "
                  f"slope={tr['slope']:+.3f} mean={tr['mean']:.2f}")
            print(f"  {'':20s} series={tr['series']}")

        # JSON output
        output_path = Path("demo_multi_match_report.json")
        output = {
            "team_id": BARCA_TEAM_ID,
            "matches": match_summary,
            "trends": trends,
        }
        output_path.write_text(
            json.dumps(output, indent=2, default=str), encoding="utf-8",
        )
        print(f"\n  Rapor → {output_path.absolute()}")

    print(f"\n{'='*70}\n  Multi-match demo tamam — {len(match_summary)} maç işlendi\n{'='*70}\n")
    return output


def main() -> int:
    try:
        run_demo()
        return 0
    except Exception as e:
        log.error("multi-match demo başarısız: %s", e)
        print(f"\n[HATA] {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
