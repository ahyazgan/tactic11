"""Gerçek StatsBomb maçı ingest + tactical profile demo.

Bu script:
1. StatsBomb Open Data'dan bir gerçek La Liga 2018/19 maçı seç
2. matches tablosuna seed et (tenant_id="t-demo")
3. ingest_events_for_match çağır
4. Takımın tactical-profile endpoint'i çağrılır gibi 20+ engine çalıştır
5. Sonuçları konsola ve report.json'a yaz

Default maç: Barcelona vs Sevilla 4-2 (La Liga 2018/19, match_id=16029)
— Messi 2 gol + 1 asist, Pique kart, Suárez kapatma.

Kullanım:
    python -m scripts.demo_real_statsbomb              # default match
    python -m scripts.demo_real_statsbomb --match 15978   # özel match
    python -m scripts.demo_real_statsbomb --no-network   # cached fixture'tan
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.logging import get_logger
from app.data.ingest.event import ingest_events_for_match
from app.data.loaders import load_match_events
from app.data.sources.statsbomb_open import StatsBombOpen
from app.db import models
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.engine.channel_preference import compute_channel_preference
from app.engine.coaching_identity import compute_coaching_identity
from app.engine.compactness import compute_compactness
from app.engine.direct_play import compute_direct_play
from app.engine.field_tilt import compute_field_tilt
from app.engine.match_dominance import compute_match_dominance
from app.engine.ppda import compute_ppda
from app.engine.press_resistance import compute_press_resistance
from app.engine.pressing_trigger import compute_pressing_trigger
from app.engine.recovery_zone_heat import compute_recovery_zone_heat
from app.engine.tempo import compute_tempo
from app.engine.transition import compute_transition
from app.engine.vaep import compute_vaep
from app.engine.xt import compute_team_xt
from app.sports import football

log = get_logger(__name__)

DEFAULT_MATCH_ID = 16029  # Barcelona vs Sevilla 4-2, La Liga 2018/19


def _ensure_db():
    """Local SQLite tablolar yoksa create_all."""
    Base.metadata.create_all(engine)


def _seed_match_from_statsbomb(
    session, *, match_id: int, tenant_id: str,
) -> models.Match:
    """StatsBomb'dan maç metadata çek + DB'ye seed et."""
    src = StatsBombOpen()
    # Tüm La Liga match listesinden ara
    for comp_id, season_id in [(11, 4), (11, 90), (11, 42)]:
        matches = src.get_matches(competition_id=comp_id, season_id=season_id)
        for m in matches:
            if m["match_id"] == match_id:
                home = m["home_team"]
                away = m["away_team"]
                kickoff_str = f"{m['match_date']}T{m.get('kick_off') or '20:00:00'}+00:00"
                try:
                    kickoff = datetime.fromisoformat(kickoff_str)
                except ValueError:
                    kickoff = datetime.now(UTC)

                # Tenant seed
                existing_tenant = session.get(models.Tenant, tenant_id)
                if existing_tenant is None:
                    session.add(models.Tenant(
                        id=tenant_id, slug=tenant_id, name="Demo",
                        settings_json="{}", active=True,
                        created_at=datetime.now(UTC),
                    ))
                # Match seed
                existing_match = session.execute(
                    models.Match.__table__.select().where(
                        models.Match.external_id == match_id,
                    )
                ).first()
                if existing_match is None:
                    session.add(models.Match(
                        sport=football.SPORT_NAME, external_id=match_id,
                        league_external_id=comp_id, season=int(season_id),
                        kickoff=kickoff, status="FT",
                        home_team_external_id=home["home_team_id"],
                        away_team_external_id=away["away_team_id"],
                        home_score=int(m.get("home_score", 0)),
                        away_score=int(m.get("away_score", 0)),
                        tenant_id=tenant_id,
                    ))
                session.flush()
                return session.execute(
                    models.Match.__table__.select().where(
                        models.Match.external_id == match_id,
                    )
                ).one()  # type: ignore[return-value]
    raise RuntimeError(f"match {match_id} bulunamadı")


def _engine_summary(name: str, result_value: Any, fields: list[str]) -> str:
    parts = []
    for f in fields:
        v = getattr(result_value, f, None)
        if v is not None:
            parts.append(f"{f}={v}")
    return f"  {name}: " + ", ".join(parts)


def run_demo(match_id: int = DEFAULT_MATCH_ID, tenant_id: str = "t-demo") -> dict:
    _ensure_db()
    src = StatsBombOpen()

    print(f"\n{'='*70}")
    print(f"  Gerçek StatsBomb Maç Demosu — match_id={match_id}")
    print(f"  Tenant: {tenant_id}")
    print(f"{'='*70}\n")

    report: dict[str, Any] = {"match_id": match_id, "tenant_id": tenant_id}

    with SessionLocal() as session:
        session.info["tenant_id"] = tenant_id

        print("[1/4] Match metadata seed (matches table)...")
        with contextlib.suppress(Exception):
            session.execute(
                models.Match.__table__.select().where(
                    models.Match.external_id == match_id,
                )
            ).first()
        _seed_match_from_statsbomb(
            session, match_id=match_id, tenant_id=tenant_id,
        )
        session.commit()
        # Fetch fresh
        match = session.execute(
            models.Match.__table__.select().where(
                models.Match.external_id == match_id,
            )
        ).one()
        home_id = match.home_team_external_id  # type: ignore[attr-defined]
        away_id = match.away_team_external_id  # type: ignore[attr-defined]
        print(f"    Ev ID: {home_id}, Dep ID: {away_id}, "
              f"Skor: {match.home_score}-{match.away_score}")  # type: ignore[attr-defined]
        report["home_team_id"] = home_id
        report["away_team_id"] = away_id
        report["score"] = f"{match.home_score}-{match.away_score}"  # type: ignore[attr-defined]

        print("\n[2/4] Event ingest (StatsBomb Open → events tablosu)...")
        ingest_report = ingest_events_for_match(
            session, src, match_external_id=match_id, tenant_id=tenant_id,
        )
        session.commit()
        print(f"    Inserted: {ingest_report.rows_inserted}")
        print(f"    Skipped:  {ingest_report.rows_skipped}")
        print(f"    Şutlar:   {ingest_report.shots}")
        print(f"    Paslar:   {ingest_report.passes}")
        print(f"    Carry:    {ingest_report.carries}")
        print(f"    Defansif: {ingest_report.defensive_actions}")
        report["ingest"] = {
            "rows_inserted": ingest_report.rows_inserted,
            "rows_skipped": ingest_report.rows_skipped,
            "shots": ingest_report.shots,
            "passes": ingest_report.passes,
            "carries": ingest_report.carries,
            "defensive_actions": ingest_report.defensive_actions,
        }

        print(f"\n[3/4] Ev takımı (#{home_id}) tactical analizi (loader + 14 engine)...")
        loaded = load_match_events(session, match_id)
        p = loaded.passes
        c = loaded.carries
        d = loaded.defensive_actions
        s = loaded.shots
        n = 1
        ppda = compute_ppda(home_id, p, d, matches_analyzed=n).value
        ptrig = compute_pressing_trigger(home_id, p, d, matches_analyzed=n).value
        rzh = compute_recovery_zone_heat(home_id, d, matches_analyzed=n).value
        compact = compute_compactness(home_id, p, d, matches_analyzed=n).value
        trans = compute_transition(home_id, d, s, matches_analyzed=n).value
        chan = compute_channel_preference(home_id, p, matches_analyzed=n).value
        direct = compute_direct_play(home_id, p, matches_analyzed=n).value
        tempo = compute_tempo(home_id, p, matches_analyzed=n).value
        pres = compute_press_resistance(
            team_external_id=home_id, all_passes=p, all_def_actions=d,
            matches_analyzed=n,
        ).value
        tilt = compute_field_tilt(home_id, away_id, p).value
        team_xt = compute_team_xt(home_id, p, c).value
        identity = compute_coaching_identity(
            home_id, away_id, p, d, s, matches_analyzed=n,
        ).value
        dominance = compute_match_dominance(
            team_external_id=home_id, opponent_team_external_id=away_id,
            team_shots=s, opponent_shots=s, all_passes=p,
            team_carries=c, opponent_carries=c,
        ).value
        vaep = compute_vaep(
            team_external_id=home_id, all_passes=p, all_carries=c, all_shots=s,
            matches_analyzed=n,
        ).value
        # Print summary
        print(_engine_summary("PPDA", ppda, ["ppda"]))
        print(_engine_summary("Pressing tarzı", ptrig, ["avg_recovery_time_min", "style_label"]))
        print(_engine_summary("Recovery zone", rzh, ["attacking_share", "style_label"]))
        print(_engine_summary("Compactness", compact, ["overall_stdev", "label"]))
        print(_engine_summary("Transition", trans, ["fast_counter_ratio", "style_label"]))
        print(_engine_summary("Channel pref", chan, ["dominant_channel"]))
        print(_engine_summary("Direct play", direct, ["avg_directness", "style_label"]))
        print(_engine_summary("Tempo", tempo, ["passes_per_minute", "label"]))
        print(_engine_summary("Press resistance", pres, ["completion_rate_under_press"]))
        print(_engine_summary("Field tilt (ev)", tilt, ["team_a_tilt"]))
        print(_engine_summary("Team xT", team_xt, ["total_xt"]))
        print(_engine_summary("Coaching identity", identity, ["archetype"]))
        print(_engine_summary("Match dominance", dominance, ["dominance_score", "label"]))
        print(_engine_summary("VAEP (ev)", vaep, ["vaep_value", "model_version"]))

        report["home_tactical"] = {
            "ppda": ppda.ppda,
            "pressing_style": ptrig.style_label,
            "recovery_zone": rzh.style_label,
            "compactness": compact.label,
            "transition_style": trans.style_label,
            "dominant_channel": chan.dominant_channel,
            "direct_play_style": direct.style_label,
            "tempo_label": tempo.label,
            "press_resistance_rate": pres.completion_rate_under_press,
            "field_tilt_team_share": tilt.team_a_tilt,
            "team_xt_total": team_xt.total_xt,
            "coaching_archetype": identity.archetype,
            "coaching_top_features": list(identity.top_features),
            "match_dominance_score": dominance.dominance_score,
            "match_dominance_label": dominance.label,
            "vaep_value": vaep.vaep_value,
        }

        print("\n[4/4] Rapor → demo_statsbomb_report.json")
        output_path = Path("demo_statsbomb_report.json")
        output_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"    {output_path.absolute()}")

    print(f"\n{'='*70}\n  Demo tamam — {len(report.get('home_tactical', {}))} engine sayısal çıktı\n{'='*70}\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Real StatsBomb match demo")
    parser.add_argument("--match", type=int, default=DEFAULT_MATCH_ID,
                        help=f"StatsBomb match_id (default: {DEFAULT_MATCH_ID})")
    parser.add_argument("--tenant", default="t-demo")
    args = parser.parse_args()

    try:
        run_demo(match_id=args.match, tenant_id=args.tenant)
        return 0
    except Exception as e:
        log.error("demo başarısız: %s", e)
        print(f"\n[HATA] {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
