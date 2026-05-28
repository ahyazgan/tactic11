"""Full La Liga 2018/19 ingest + 56 engine signal/noise audit.

Hedef: gerçek sezon datası üzerinde hangi engine'in gerçek sinyal verdiği,
hangisinin sentetik test'te güzel görünüp prod'da gürültü olduğu kanıtla.

Akış:
1. StatsBomb Open'dan La Liga 2018/19 tüm 34 maçı ingest
2. Her takım için tactical-profile pattern'iyle 19+ team-level engine
3. Engine başına audit:
   - non-null rate (kaç maç-takım için anlamlı çıktı)
   - variance (CV = stdev/mean; 0.05 altı sinyal yok)
   - Barca için known fact validation (Pep tarzı: yüksek tilt, düşük PPDA)
4. Çıktı: full_season_audit.json + markdown report

Kullanım:
    DATABASE_URL="sqlite:///full_season.db" \\
        python -m scripts.full_season_audit
"""

from __future__ import annotations

import json
import math
import statistics
import sys
import time
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.core.logging import get_logger
from app.data.ingest.event import ingest_events_for_match
from app.data.loaders import load_match_events
from app.data.sources.statsbomb_open import StatsBombOpen
from app.db import models
from app.db.base import Base
from app.db.session import SessionLocal, engine as db_engine
from app.engine.build_up_pattern import compute_build_up_pattern
from app.engine.channel_preference import compute_channel_preference
from app.engine.coaching_identity import compute_coaching_identity
from app.engine.compactness import compute_compactness
from app.engine.counter_press_triggers import compute_counter_press_triggers
from app.engine.cross_effectiveness import compute_cross_effectiveness
from app.engine.cutback_frequency import compute_cutback_frequency
from app.engine.defensive_duels import compute_defensive_duels
from app.engine.defensive_line import compute_defensive_line
from app.engine.direct_play import compute_direct_play
from app.engine.field_tilt import compute_field_tilt
from app.engine.final_third_entries import compute_final_third_entries
from app.engine.match_dominance import compute_match_dominance
from app.engine.possession_quality import compute_possession_quality
from app.engine.ppda import compute_ppda
from app.engine.press_resistance import compute_press_resistance
from app.engine.pressing_trigger import compute_pressing_trigger
from app.engine.recovery_zone_heat import compute_recovery_zone_heat
from app.engine.set_piece_zones import compute_set_piece_zones
from app.engine.tempo import compute_tempo
from app.engine.transition import compute_transition
from app.engine.xt import compute_team_xt
from app.sports import football
from scripts.demo_real_statsbomb import _seed_match_from_statsbomb

log = get_logger(__name__)

LA_LIGA_COMP_ID = 11
LA_LIGA_SEASON_ID_201819 = 4
BARCA_TEAM_ID = 217
TENANT_ID = "t-audit"

# Engine başına extract function: (engine_name, metric_path, output_type)
TEAM_ENGINES: list[dict[str, Any]] = [
    {"name": "ppda", "metric": "ppda", "lower_is_better": True},
    {"name": "pressing_trigger", "metric": "avg_recovery_time_min",
     "lower_is_better": True},
    {"name": "recovery_zone_heat", "metric": "attacking_share"},
    {"name": "defensive_line", "metric": "avg_x"},
    {"name": "compactness", "metric": "overall_stdev"},
    {"name": "transition", "metric": "fast_counter_ratio"},
    {"name": "counter_press_triggers", "metric": "pressure_responses"},
    {"name": "direct_play", "metric": "avg_directness"},
    {"name": "tempo", "metric": "passes_per_minute"},
    {"name": "possession_quality", "metric": "quality_score"},
    {"name": "channel_preference", "metric": "left_share"},
    {"name": "final_third_entries", "metric": "total_entries"},
    {"name": "cross_effectiveness", "metric": "total_crosses"},
    {"name": "cutback_frequency", "metric": "cutbacks"},
    {"name": "defensive_duels", "metric": "win_rate"},
    {"name": "press_resistance", "metric": "completion_rate_under_press"},
    {"name": "set_piece_zones", "metric": "total_shots"},
    {"name": "build_up_pattern", "metric": "long_ball_ratio"},
    {"name": "team_xt", "metric": "total_xt"},
    {"name": "field_tilt", "metric": "team_a_tilt"},
    {"name": "match_dominance", "metric": "dominance_score"},
    {"name": "coaching_identity_archetype",
     "metric": "archetype"},  # kategorik
]


def ensure_db():
    Base.metadata.create_all(db_engine)


def ingest_full_season(src: StatsBombOpen, max_matches: int | None = None) -> list[int]:
    """Tüm La Liga 2018/19 maçlarını ingest et."""
    matches = src.get_matches(
        competition_id=LA_LIGA_COMP_ID, season_id=LA_LIGA_SEASON_ID_201819,
    )
    if max_matches:
        matches = matches[:max_matches]
    print(f"\n[1/3] {len(matches)} maç ingest ediliyor...")
    ingested: list[int] = []
    with SessionLocal() as session:
        session.info["tenant_id"] = TENANT_ID
        for i, m in enumerate(matches, 1):
            mid = m["match_id"]
            try:
                _seed_match_from_statsbomb(session, match_id=mid, tenant_id=TENANT_ID)
                session.commit()
                report = ingest_events_for_match(
                    session, src, match_external_id=mid, tenant_id=TENANT_ID,
                )
                session.commit()
                ingested.append(mid)
                print(f"  [{i}/{len(matches)}] match {mid}: "
                      f"{report.rows_inserted} event (skip {report.rows_skipped})")
            except Exception as e:
                print(f"  [{i}/{len(matches)}] match {mid} FAIL: {str(e)[:60]}")
    return ingested


def _team_engines_for_match(
    session, match_external_id: int, team_id: int, opponent_id: int,
) -> dict[str, dict[str, Any]]:
    """Bir maçta bir takım için 22 engine'i çalıştır + metric path'i çıkar."""
    loaded = load_match_events(session, match_external_id)
    if loaded.total == 0:
        return {}
    p = loaded.passes
    c = loaded.carries
    d = loaded.defensive_actions
    s = loaded.shots
    results: dict[str, dict[str, Any]] = {}

    def _try(name: str, fn):
        try:
            results[name] = fn().value.__dict__ if hasattr(fn().value, "__dict__") else {}
            v = fn().value
            results[name] = {
                k: getattr(v, k) for k in dir(v)
                if not k.startswith("_") and not callable(getattr(v, k))
            }
        except Exception as e:
            results[name] = {"error": str(e)[:80]}

    _try("ppda", lambda: compute_ppda(team_id, p, d))
    _try("pressing_trigger", lambda: compute_pressing_trigger(team_id, p, d))
    _try("recovery_zone_heat", lambda: compute_recovery_zone_heat(team_id, d))
    _try("defensive_line", lambda: compute_defensive_line(team_id, d))
    _try("compactness", lambda: compute_compactness(team_id, p, d))
    _try("transition", lambda: compute_transition(team_id, d, s))
    _try("counter_press_triggers", lambda: compute_counter_press_triggers(team_id, p, d))
    _try("direct_play", lambda: compute_direct_play(team_id, p))
    _try("tempo", lambda: compute_tempo(team_id, p))
    _try("possession_quality", lambda: compute_possession_quality(team_id, p, s))
    _try("channel_preference", lambda: compute_channel_preference(team_id, p))
    _try("final_third_entries", lambda: compute_final_third_entries(team_id, p, c))
    _try("cross_effectiveness", lambda: compute_cross_effectiveness(team_id, p, s))
    _try("cutback_frequency", lambda: compute_cutback_frequency(team_id, p, s))
    _try("defensive_duels",
         lambda: compute_defensive_duels(team_external_id=team_id, all_def_actions=d))
    _try("press_resistance",
         lambda: compute_press_resistance(
             team_external_id=team_id, all_passes=p, all_def_actions=d))
    _try("set_piece_zones", lambda: compute_set_piece_zones(team_id, s))
    _try("build_up_pattern", lambda: compute_build_up_pattern(team_id, p, s))
    _try("team_xt", lambda: compute_team_xt(team_id, p, c))
    _try("field_tilt", lambda: compute_field_tilt(team_id, opponent_id, p))
    _try("match_dominance", lambda: compute_match_dominance(
        team_external_id=team_id, opponent_team_external_id=opponent_id,
        team_shots=s, opponent_shots=s, all_passes=p, team_carries=c,
        opponent_carries=c,
    ))
    _try("coaching_identity_archetype", lambda: compute_coaching_identity(
        team_id, opponent_id, p, d, s,
    ))
    return results


def run_audit(match_ids: list[int]) -> dict[str, Any]:
    """Her ingest edilen maç için her takıma 22 engine çalıştır + audit."""
    print(f"\n[2/3] {len(match_ids)} maç üzerinde engine audit...")
    # team_id -> engine_name -> [values across matches]
    by_team_engine: dict[int, dict[str, list[float]]] = {}
    # Archetype counts (categorical)
    archetype_counts: dict[int, dict[str, int]] = {}

    with SessionLocal() as session:
        session.info["tenant_id"] = TENANT_ID
        for i, mid in enumerate(match_ids, 1):
            match = session.execute(
                select(models.Match).where(
                    models.Match.sport == football.SPORT_NAME,
                    models.Match.external_id == mid,
                )
            ).scalar_one_or_none()
            if not match:
                continue
            home_id = match.home_team_external_id
            away_id = match.away_team_external_id
            for team_id, opp_id in [(home_id, away_id), (away_id, home_id)]:
                results = _team_engines_for_match(session, mid, team_id, opp_id)
                if not results:
                    continue
                by_team_engine.setdefault(team_id, {})
                archetype_counts.setdefault(team_id, {})
                for spec in TEAM_ENGINES:
                    eng_name = spec["name"]
                    metric_key = spec["metric"]
                    if eng_name not in results:
                        continue
                    r = results[eng_name]
                    if "error" in r:
                        continue
                    val = r.get(metric_key)
                    if eng_name == "coaching_identity_archetype":
                        # Categorical
                        if isinstance(val, str):
                            archetype_counts[team_id][val] = (
                                archetype_counts[team_id].get(val, 0) + 1
                            )
                    elif isinstance(val, (int, float)) and not math.isinf(val):
                        by_team_engine[team_id].setdefault(eng_name, []).append(float(val))
            if i % 5 == 0:
                print(f"  [{i}/{len(match_ids)}]")

    return {"by_team_engine": by_team_engine, "archetype_counts": archetype_counts}


def signal_audit(by_team_engine: dict[int, dict[str, list[float]]]) -> dict[str, Any]:
    """Engine başına: variance (CV), non-null rate, takım-arası farkı."""
    # Tüm takım sample'larını engine başına birleştir
    engine_samples: dict[str, list[float]] = {}
    engine_by_team: dict[str, dict[int, float]] = {}
    for team_id, engine_vals in by_team_engine.items():
        for eng, vals in engine_vals.items():
            engine_samples.setdefault(eng, []).extend(vals)
            if vals:
                engine_by_team.setdefault(eng, {})[team_id] = (
                    statistics.mean(vals)
                )

    audit: dict[str, dict[str, Any]] = {}
    for eng, samples in engine_samples.items():
        if not samples:
            audit[eng] = {"verdict": "DEAD", "reason": "no samples"}
            continue
        mean = statistics.mean(samples)
        stdev = statistics.pstdev(samples) if len(samples) > 1 else 0.0
        cv = (stdev / abs(mean)) if mean != 0 else 0.0
        team_means = engine_by_team.get(eng, {})
        team_spread = (
            (max(team_means.values()) - min(team_means.values()))
            if len(team_means) > 1 else 0.0
        )
        # Verdict heuristic:
        # - Sample sayısı az → INSUFFICIENT
        # - CV < 0.05 ve team_spread / |mean| < 0.10 → NO_SIGNAL (gürültü)
        # - CV > 0.30 veya team_spread anlamlı → STRONG_SIGNAL
        # - Aksi → MODERATE
        n = len(samples)
        if n < 20:
            verdict = "INSUFFICIENT_DATA"
        elif cv < 0.05 and (team_spread / abs(mean) if mean != 0 else 0) < 0.10:
            verdict = "NO_SIGNAL"
        elif cv >= 0.30 or (team_spread / abs(mean) if mean != 0 else 0) >= 0.30:
            verdict = "STRONG_SIGNAL"
        else:
            verdict = "MODERATE"
        audit[eng] = {
            "n_samples": n,
            "mean": round(mean, 4),
            "stdev": round(stdev, 4),
            "cv": round(cv, 4),
            "team_spread": round(team_spread, 4),
            "n_teams": len(team_means),
            "verdict": verdict,
        }
    return audit


def barca_validation(by_team_engine: dict[int, dict[str, list[float]]]) -> dict[str, str]:
    """Bilinen gerçeklerle Barca verisi karşılaştır.

    Pep-sonrası Valverde Barca beklenen:
    - field_tilt > 0.6 (yüksek hücum hakimiyeti)
    - direct_play < 0.5 (possession-ağırlık)
    - tempo > 6 (yüksek pas hızı)
    - team_xt > 1.5 / maç (yaratıcı)
    - dominance_score > 1.5
    """
    barca = by_team_engine.get(BARCA_TEAM_ID, {})
    results: dict[str, str] = {}
    expectations = {
        "field_tilt": (0.6, "high"),  # > 0.6 ev/dep ortalaması
        "direct_play": (0.5, "low"),   # < 0.5
        "tempo": (6.0, "high"),
        "team_xt": (1.5, "high"),
        "match_dominance": (1.5, "high"),
    }
    for eng, (threshold, expected) in expectations.items():
        vals = barca.get(eng, [])
        if not vals:
            results[eng] = "NO_DATA"
            continue
        mean = statistics.mean(vals)
        if expected == "high":
            results[eng] = f"OK (mean {mean:.2f} >= {threshold})" \
                if mean >= threshold else f"MISS (mean {mean:.2f} < {threshold})"
        else:
            results[eng] = f"OK (mean {mean:.2f} < {threshold})" \
                if mean < threshold else f"MISS (mean {mean:.2f} >= {threshold})"
    return results


def write_report(
    audit: dict[str, Any], barca_val: dict[str, str],
    archetype_counts: dict[int, dict[str, int]],
    n_matches: int,
) -> None:
    """JSON + Markdown rapor."""
    Path("full_season_audit.json").write_text(
        json.dumps({
            "audit": audit,
            "barca_validation": barca_val,
            "archetype_counts": {str(k): v for k, v in archetype_counts.items()},
            "n_matches_analyzed": n_matches,
        }, indent=2, default=str),
        encoding="utf-8",
    )

    # Markdown — ranked engines
    sorted_engines = sorted(
        audit.items(),
        key=lambda kv: (
            {"STRONG_SIGNAL": 0, "MODERATE": 1, "INSUFFICIENT_DATA": 2,
             "NO_SIGNAL": 3, "DEAD": 4}.get(kv[1]["verdict"], 5),
            -kv[1].get("cv", 0),
        ),
    )
    lines: list[str] = [
        "# Full Season Engine Audit",
        "",
        f"La Liga 2018/19 üzerinde {n_matches} maç ingest + 22 team-level engine audit.",
        "",
        "## Engine Rankings (signal → noise)",
        "",
        "| Engine | Verdict | CV | n | Team Spread | Mean |",
        "|---|---|---|---|---|---|",
    ]
    for eng, info in sorted_engines:
        lines.append(
            f"| `{eng}` | **{info['verdict']}** | "
            f"{info.get('cv', 0):.3f} | {info.get('n_samples', 0)} | "
            f"{info.get('team_spread', 0):.3f} | "
            f"{info.get('mean', 0):.3f} |"
        )
    lines.append("")
    lines.append("## Barca Sanity Check")
    lines.append("")
    for eng, verdict in barca_val.items():
        lines.append(f"- `{eng}`: {verdict}")
    lines.append("")
    lines.append("## Barca Coaching Archetype Distribution")
    lines.append("")
    barca_arch = archetype_counts.get(BARCA_TEAM_ID, {})
    for arch, count in sorted(barca_arch.items(), key=lambda x: -x[1]):
        lines.append(f"- `{arch}`: {count} maç")
    Path("full_season_audit.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser_args = sys.argv[1:]
    max_matches: int | None = None
    if "--max" in parser_args:
        idx = parser_args.index("--max")
        max_matches = int(parser_args[idx + 1])

    print(f"\n{'='*70}")
    print(f"  Full Season Audit — La Liga 2018/19")
    print(f"  Max matches: {max_matches or 'all'}")
    print(f"{'='*70}")
    ensure_db()
    src = StatsBombOpen()
    started = time.time()

    match_ids = ingest_full_season(src, max_matches=max_matches)
    print(f"\n  Ingest tamam: {len(match_ids)} maç "
          f"({time.time() - started:.0f} sn)")

    audit_result = run_audit(match_ids)
    by_team_engine = audit_result["by_team_engine"]
    archetype_counts = audit_result["archetype_counts"]
    print(f"\n  Audit tamam: {len(by_team_engine)} takım örneği "
          f"({time.time() - started:.0f} sn)")

    signal = signal_audit(by_team_engine)
    barca_val = barca_validation(by_team_engine)

    print("\n[3/3] Rapor yazılıyor → full_season_audit.json + .md")
    write_report(signal, barca_val, archetype_counts, len(match_ids))

    # Konsol özet
    print(f"\n{'='*70}")
    print(f"  SIGNAL RANKING")
    print(f"{'='*70}")
    by_verdict: dict[str, list[str]] = {}
    for eng, info in signal.items():
        by_verdict.setdefault(info["verdict"], []).append(eng)
    for v in ["STRONG_SIGNAL", "MODERATE", "INSUFFICIENT_DATA",
              "NO_SIGNAL", "DEAD"]:
        engs = by_verdict.get(v, [])
        if engs:
            print(f"\n{v} ({len(engs)}):")
            for e in engs:
                info = signal[e]
                print(f"  · {e}  CV={info.get('cv', 0):.2f}  "
                      f"spread={info.get('team_spread', 0):.2f}  "
                      f"n={info.get('n_samples', 0)}")

    print(f"\n{'='*70}")
    print(f"  BARCA SANITY")
    print(f"{'='*70}")
    for eng, v in barca_val.items():
        print(f"  · {eng}: {v}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
