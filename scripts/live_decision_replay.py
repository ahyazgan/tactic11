"""Live decision replay — gerçek La Liga maçında orkestra şefi demosu.

Bir maçı dakika-dakika "replay" eder; her tick'te 10 engine'in birleşik
karar panelini ve context_engine'in tek "ŞİMDİ şunu yap" çıktısını basar.

Kullanım:
    python -m scripts.live_decision_replay                  # default match
    python -m scripts.live_decision_replay --match 16029    # Barcelona-Sevilla
    python -m scripts.live_decision_replay --star 5503      # yıldız = Messi
    python -m scripts.live_decision_replay --ticks 60,75,85 # spesifik dakikalar

Gerçek StatsBomb verisi — replay modu (event-window proxy). Gerçek canlı
feed bağlanınca aynı pipeline çalışır.
"""
from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime

from app.data.ingest.event import ingest_events_for_match
from app.data.loaders import load_match_events
from app.data.sources.statsbomb_open import StatsBombOpen
from app.db import models
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.engine.closing_strategy import compute_closing_strategy
from app.engine.foul_pressure import compute_foul_pressure
from app.engine.live_risk_monitor import compute_live_risk_monitor
from app.engine.live_tactical_trigger import compute_live_tactical_trigger
from app.engine.momentum_tracker import compute_momentum
from app.engine.star_feed import compute_star_feed
from app.engine.sub_timing import compute_sub_timing
from app.sports import football

DEFAULT_MATCH_ID = 16029   # Barcelona-Sevilla 4-2, La Liga 2018/19
DEFAULT_STAR_ID = 5503     # Lionel Messi (Barcelona)
DEFAULT_TICKS = (60.0, 70.0, 80.0, 90.0)


def _ensure_db() -> None:
    Base.metadata.create_all(engine)


def _seed_match(session, *, match_id: int, tenant_id: str) -> models.Match:
    """StatsBomb meta + tenant + match seed. Idempotent."""
    src = StatsBombOpen()
    for comp_id, season_id in [(11, 4), (11, 90), (11, 42)]:
        matches = src.get_matches(competition_id=comp_id, season_id=season_id)
        for m in matches:
            if m["match_id"] != match_id:
                continue
            home, away = m["home_team"], m["away_team"]
            ko_str = f"{m['match_date']}T{m.get('kick_off') or '20:00:00'}+00:00"
            try:
                kickoff = datetime.fromisoformat(ko_str)
            except ValueError:
                kickoff = datetime.now(UTC)
            if session.get(models.Tenant, tenant_id) is None:
                session.add(models.Tenant(
                    id=tenant_id, slug=tenant_id, name="Replay",
                    settings_json="{}", active=True,
                    created_at=datetime.now(UTC),
                ))
            existing = session.execute(
                models.Match.__table__.select().where(
                    models.Match.external_id == match_id,
                )
            ).first()
            if existing is None:
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
                session.commit()
            return session.execute(
                models.Match.__table__.select().where(
                    models.Match.external_id == match_id,
                )
            ).one()
    raise RuntimeError(f"match {match_id} bulunamadı")


def _hr(char: str = "─", w: int = 70) -> str:
    return char * w


def _tick_panel(
    session, match: models.Match, my_team_id: int, minute: float,
    star_player_id: int,
) -> None:
    """Tek dakika için 10 engine + orkestra çıktısı."""
    loaded = load_match_events(session, match.external_id)
    p = [x for x in loaded.passes if x.minute <= minute]
    d = [x for x in loaded.defensive_actions if x.minute <= minute]
    s = [x for x in loaded.shots if x.minute <= minute]

    home_id = match.home_team_external_id
    opp_id = match.away_team_external_id if my_team_id == home_id else home_id
    my_score = match.home_score if my_team_id == home_id else match.away_score
    opp_score = match.away_score if my_team_id == home_id else match.home_score
    my_score, opp_score = int(my_score or 0), int(opp_score or 0)

    print(f"\n{_hr('═')}")
    print(f"  {int(minute):3}. dakika  |  Skor (replay-sabit FT): "
          f"{my_score}-{opp_score}  |  Olay sayısı: {len(p)+len(d)+len(s)}")
    print(_hr())

    mom = compute_momentum(
        my_team_id, opp_id, p, d, s, current_minute=minute,
    ).value
    print(f"  Momentum     │ holder={mom.momentum_holder:9s} "
          f"score={mom.momentum_score:+.2f}  "
          f"press_break={mom.press_breaking}  xg_swing={mom.xg_swing_alert}")
    if mom.alert_text:
        print(f"               └ {mom.alert_text}")

    timing = compute_sub_timing(
        my_team_id, p, d, current_minute=minute,
        my_score=my_score, opponent_score=opp_score,
    ).value
    nowadv = [a for a in timing.advices if a.timing_verdict == "now"]
    pkg = list(timing.package_recommendation)
    print(f"  Sub timing   │ now={len(nowadv)}  paket={pkg or '—'}")
    if timing.package_rationale and "gerekmiyor" not in timing.package_rationale:
        print(f"               └ {timing.package_rationale}")

    trig = compute_live_tactical_trigger(
        my_team_id, current_minute=minute,
        my_score=my_score, opponent_score=opp_score,
        momentum_score=mom.momentum_score,
    ).value
    active = [t for t in trig.triggers if t.fired]
    print(f"  Tac trigger  │ {len(active)} aktif  ({trig.score_state})")
    for t in active[:2]:
        print(f"               └ [{t.urgency:6s}] {t.recommendation}")

    risk = compute_live_risk_monitor(
        my_team_id, [], current_minute=minute,
        my_score=my_score, opponent_score=opp_score,
    ).value
    print(f"  Risk monitor │ {risk.time_management}")

    cs = compute_closing_strategy(
        my_team_id, current_minute=minute,
        my_score=my_score, opponent_score=opp_score,
        momentum_score=mom.momentum_score,
    ).value
    print(f"  Closing      │ {cs.key_message}")
    print(f"               └ tempo={cs.recipe.tempo}, "
          f"ikame={cs.recipe.sub_priority}, "
          f"risk_al={cs.risk_reward.take_risk}")

    sf = compute_star_feed(
        my_team_id, star_player_id=star_player_id,
        passes=p, shots=s, current_minute=minute,
    ).value
    print(f"  Star feed    │ {sf.involvement_state:9s} "
          f"({sf.pass_share_pct:5.1f}% pas, {sf.suggested_action})")
    if sf.involvement_state in ("starved", "well-fed"):
        print(f"               └ {sf.tactical_advice}")

    # I.1: ingest edilmiş faul event'lerini kullan (yoksa engine boşa çalışır)
    fouls_so_far = [f for f in loaded.fouls if f.minute <= minute]
    fp = compute_foul_pressure(
        my_team_id, opp_id, fouls_so_far, current_minute=minute,
    ).value
    print(f"  Foul pres.   │ {len(fouls_so_far)} faul "
          f"(rakip:{fp.opp_fouls_window}/15dk, hakem:{fp.referee_card_pressure})")
    if fp.tactical_fouling_alert or fp.our_high_foul_alert or fp.escalation_alert:
        print(f"               └ {fp.tactical_advice}")


def _run(
    *, match_id: int, my_team_id: int | None, star_player_id: int,
    ticks: tuple[float, ...], tenant_id: str,
) -> int:
    _ensure_db()
    session = SessionLocal()
    session.info["tenant_id"] = tenant_id
    try:
        print(f"\n{_hr('▓')}")
        print(f"  Live Decision Replay — match {match_id}")
        print(_hr('▓'))

        match = _seed_match(session, match_id=match_id, tenant_id=tenant_id)
        # ORM instance — attribute erişimi için
        match = session.query(models.Match).filter_by(
            sport=football.SPORT_NAME, external_id=match_id,
        ).one()

        # my_team default = home team
        if my_team_id is None:
            my_team_id = match.home_team_external_id
        opp = (match.away_team_external_id if my_team_id == match.home_team_external_id
               else match.home_team_external_id)
        print(f"  Skor (FT): {match.home_score}-{match.away_score}  |  "
              f"Bizim takım: {my_team_id} vs {opp}")
        print(f"  Yıldız: {star_player_id}  |  Ticks: "
              f"{', '.join(str(int(t)) for t in ticks)}")

        # Ingest events
        print("\n  StatsBomb events ingest...")
        result = ingest_events_for_match(
            session, source=StatsBombOpen(),
            match_external_id=match_id, tenant_id=tenant_id,
        )
        session.commit()  # ingest flush yapar; commit etmeden context close → rollback
        print(f"  → {result.rows_inserted} event eklendi "
              f"({result.shots} şut, {result.passes} pas, "
              f"{result.defensive_actions} def, {result.fouls} faul).")

        # Run replay ticks
        for tick in ticks:
            _tick_panel(session, match, my_team_id, tick, star_player_id)

        print(f"\n{_hr('▓')}\n  Replay tamam.\n{_hr('▓')}\n")
        return 0
    finally:
        session.close()


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--match", type=int, default=DEFAULT_MATCH_ID,
                   help=f"StatsBomb match_id (default {DEFAULT_MATCH_ID})")
    p.add_argument("--team", type=int, default=None,
                   help="my_team_external_id (default: home team)")
    p.add_argument("--star", type=int, default=DEFAULT_STAR_ID,
                   help=f"Yıldız oyuncu external_id (default {DEFAULT_STAR_ID} Messi)")
    p.add_argument("--ticks", type=str, default=",".join(str(int(t)) for t in DEFAULT_TICKS),
                   help="Virgül ayrılmış dakikalar, örn. 60,70,80,90")
    p.add_argument("--tenant", type=str, default="t-demo",
                   help="Tenant id (default t-demo)")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    ticks = tuple(float(t.strip()) for t in args.ticks.split(",") if t.strip())
    return _run(
        match_id=args.match, my_team_id=args.team,
        star_player_id=args.star, ticks=ticks, tenant_id=args.tenant,
    )


if __name__ == "__main__":
    raise SystemExit(main())
