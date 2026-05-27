"""Uçtan uca demo — fixture'tan sync, tüm engine'leri çalıştır, opsiyonel AI yorumu.

Kullanım:
    python scripts/demo.py                  # SQLite + fixture; minimal
    python scripts/demo.py --reset          # _demo.db'yi sıfırla, baştan
    python scripts/demo.py --league 39      # Premier League fixture'ı varsa

Üç işe yarar:
1. Yeni biri tek komutla sistemin ne yaptığını görür.
2. Deploy öncesi smoke check.
3. API_FOOTBALL_KEY/ANTHROPIC_API_KEY geldiğinde gerçek datayla aynı script.

Bölümler (mevcut tüm engine'ler):
1. Sync + DB durumu
2. Takım analizi (form + rating)
3. Fikstür yoğunluğu (engine.schedule)
4. Fikstür zorluğu (engine.fixture_difficulty — rakip rating'leriyle)
5. Head-to-Head (engine.opponent)
6. Matchup kıyas raporu (engine.matchup)
7. Maç önizleme (form+h2h sentezi)
8. Skor tahmini (engine.predict — Poisson + Dixon-Coles)

ENV davranışı:
- DATABASE_URL boşsa sqlite:///./_demo.db
- USE_FIXTURES boşsa true (anahtar yokken çalışsın)
- ANTHROPIC_API_KEY varsa AI yorumları da göster
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Defaults — gerçek .env yoksa demo'yu çalışır halde tut.
os.environ.setdefault("DATABASE_URL", "sqlite:///./_demo.db")
os.environ.setdefault("USE_FIXTURES", "true")
os.environ.setdefault("LOG_LEVEL", "WARNING")

from app.ai import AnthropicClient, ClaudeCommentator  # noqa: E402
from app.data.ingest import sync_league  # noqa: E402
from app.data.sources.api_football import APIFootball  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.engine.fixture_difficulty import compute_fixture_difficulty  # noqa: E402
from app.engine.form import compute_form  # noqa: E402
from app.engine.matchup import compute_matchup  # noqa: E402
from app.engine.opponent import compute_head_to_head  # noqa: E402
from app.engine.predict import compute_predict  # noqa: E402
from app.engine.rating import compute_team_rating  # noqa: E402
from app.engine.schedule import compute_schedule  # noqa: E402
from app.sports import football  # noqa: E402


def _hr(title: str) -> None:
    print()
    print("=" * 64)
    print(f" {title}")
    print("=" * 64)


def _row(label: str, value: object) -> None:
    print(f"  {label:.<28} {value}")


def _maybe_reset(reset: bool) -> None:
    if not reset:
        return
    db = os.environ["DATABASE_URL"]
    if db.startswith("sqlite:///"):
        path = Path(db.replace("sqlite:///", ""))
        if path.exists():
            path.unlink()
            print(f"[reset] {path} silindi")


def _alembic_check() -> None:
    """Migrasyonların güncel olduğunu doğrula; değilse upgrade et."""
    from alembic.config import Config

    from alembic import command

    cfg = Config(str(_PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_PROJECT_ROOT / "alembic"))
    command.upgrade(cfg, "head")


def _print_db_stats() -> None:
    from sqlalchemy import func, select

    from app.db import models

    _hr("DB durumu")
    with SessionLocal() as s:
        for m in (
            models.League, models.Team, models.Match, models.Snapshot,
            models.UsageEvent, models.CacheEntry, models.JobRun,
        ):
            n = s.scalar(select(func.count()).select_from(m)) or 0
            _row(m.__tablename__, n)


def _run_sync(league_id: int, season: int) -> None:
    _hr(f"Sync — league={league_id} season={season} (USE_FIXTURES={os.environ.get('USE_FIXTURES')})")
    source = APIFootball()
    with SessionLocal() as s:
        report = sync_league(s, source, league_id=league_id, season=season)
    _row("leagues yazıldı", report.leagues_written)
    _row("teams yazıldı", report.teams_written)
    _row("matches yazıldı", report.matches_written)
    _row("rejected (validation)", report.rejected_count)
    _row("snapshot id", report.snapshot_id)


def _show_team_analysis(team_id: int, *, com: ClaudeCommentator | None) -> None:
    from sqlalchemy import or_, select

    from app.db import models

    with SessionLocal() as s:
        team = s.execute(
            select(models.Team).where(
                models.Team.sport == football.SPORT_NAME,
                models.Team.external_id == team_id,
            )
        ).scalar_one_or_none()
        if team is None:
            print(f"[skip] takım {team_id} DB'de yok")
            return
        matches = list(
            s.execute(
                select(models.Match)
                .where(
                    models.Match.sport == football.SPORT_NAME,
                    or_(
                        models.Match.home_team_external_id == team_id,
                        models.Match.away_team_external_id == team_id,
                    ),
                )
                .order_by(models.Match.kickoff.desc())
            ).scalars()
        )

    _hr(f"Takım analizi — {team.name} ({team_id})")
    if not matches:
        print("  (maç yok, analiz atlandı)")
        return

    form = compute_form(team_id, matches, last_n=5)
    f = form.value
    _row("son N maç", f.matches_played)
    _row("W-D-L", f"{f.wins}-{f.draws}-{f.losses}")
    _row("goller (GF-GA, averaj)", f"{f.goals_for}-{f.goals_against} ({f.goal_diff:+d})")
    _row("maç başı puan", f.points_per_game)
    _row("son sonuçlar (yeniden eskiye)", " ".join(f.last_results) or "—")

    rating = compute_team_rating(team_id, matches, last_n=10)
    r = rating.value
    _row("rating (kompozit)", r.rating)
    _row("ppg / gdpm", f"{r.points_per_game} / {r.goal_diff_per_match:+}")

    if com is not None:
        print()
        print("  AI yorumu (form):")
        print("    " + com.explain(form).replace("\n", "\n    "))
        print()
        print("  AI yorumu (rating):")
        print("    " + com.explain(rating).replace("\n", "\n    "))


def _show_h2h(a: int, b: int, *, com: ClaudeCommentator | None) -> None:
    from sqlalchemy import or_, select

    from app.db import models

    with SessionLocal() as s:
        matches = list(
            s.execute(
                select(models.Match).where(
                    models.Match.sport == football.SPORT_NAME,
                    or_(
                        (models.Match.home_team_external_id == a)
                        & (models.Match.away_team_external_id == b),
                        (models.Match.home_team_external_id == b)
                        & (models.Match.away_team_external_id == a),
                    ),
                )
            ).scalars()
        )

    _hr(f"Head-to-Head — {a} vs {b}")
    h2h = compute_head_to_head(a, b, matches)
    v = h2h.value
    _row("oynanmış maç", v.matches_played)
    if v.matches_played > 0:
        _row(f"{a} galibiyet", v.team_a_wins)
        _row("beraberlik", v.draws)
        _row(f"{b} galibiyet", v.team_b_wins)
        _row("goller", f"{a}: {v.team_a_goals} – {b}: {v.team_b_goals}")
        if com is not None:
            print()
            print("  AI yorumu:")
            print("    " + com.explain(h2h).replace("\n", "\n    "))


def _show_preview(match_id: int, *, com: ClaudeCommentator | None) -> None:
    from sqlalchemy import or_, select

    from app.db import models

    with SessionLocal() as s:
        match = s.execute(
            select(models.Match).where(
                models.Match.sport == football.SPORT_NAME,
                models.Match.external_id == match_id,
            )
        ).scalar_one_or_none()
        if match is None:
            print(f"[skip] match {match_id} yok")
            return
        home_id = match.home_team_external_id
        away_id = match.away_team_external_id

        def _prior(team_id: int) -> list[models.Match]:
            return list(
                s.execute(
                    select(models.Match)
                    .where(
                        models.Match.sport == football.SPORT_NAME,
                        models.Match.kickoff < match.kickoff,
                        or_(
                            models.Match.home_team_external_id == team_id,
                            models.Match.away_team_external_id == team_id,
                        ),
                    )
                    .order_by(models.Match.kickoff.desc())
                ).scalars()
            )

        home_matches = _prior(home_id)
        away_matches = _prior(away_id)
        h2h_matches = list(
            s.execute(
                select(models.Match).where(
                    models.Match.sport == football.SPORT_NAME,
                    models.Match.kickoff < match.kickoff,
                    or_(
                        (models.Match.home_team_external_id == home_id)
                        & (models.Match.away_team_external_id == away_id),
                        (models.Match.home_team_external_id == away_id)
                        & (models.Match.away_team_external_id == home_id),
                    ),
                )
            ).scalars()
        )

    _hr(f"Maç önizleme — match_id={match_id} ({home_id} vs {away_id})")
    _row("kickoff", match.kickoff.isoformat())
    _row("status", match.status)
    home_form = compute_form(home_id, home_matches, last_n=5)
    away_form = compute_form(away_id, away_matches, last_n=5)
    h2h = compute_head_to_head(home_id, away_id, h2h_matches)
    _row("ev formu (W-D-L)", f"{home_form.value.wins}-{home_form.value.draws}-{home_form.value.losses}")
    _row("dep formu (W-D-L)", f"{away_form.value.wins}-{away_form.value.draws}-{away_form.value.losses}")
    _row("H2H (a-d-b)", f"{h2h.value.team_a_wins}-{h2h.value.draws}-{h2h.value.team_b_wins}")
    if com is not None:
        print()
        print("  AI brief (maç öncesi):")
        text = com.explain_match_preview(
            home_form=home_form, away_form=away_form, h2h=h2h,
            home_team_id=home_id, away_team_id=away_id,
            kickoff_iso=match.kickoff.isoformat(),
        )
        print("    " + text.replace("\n", "\n    "))


def _show_schedule(team_id: int, *, com: ClaudeCommentator | None) -> None:
    from datetime import datetime  # noqa: E402

    from sqlalchemy import or_, select

    from app.db import models

    with SessionLocal() as s:
        matches = list(
            s.execute(
                select(models.Match)
                .where(
                    models.Match.sport == football.SPORT_NAME,
                    or_(
                        models.Match.home_team_external_id == team_id,
                        models.Match.away_team_external_id == team_id,
                    ),
                )
                .order_by(models.Match.kickoff.desc())
            ).scalars()
        )

    _hr(f"Fikstür yoğunluğu — takım {team_id} (next 30 gün)")
    if not matches:
        print("  (maç yok)")
        return
    # SQLite tz-strip; API endpoint'iyle aynı pattern
    ref_tz = matches[0].kickoff.tzinfo
    now = datetime.now(ref_tz)
    result = compute_schedule(team_id, matches, now=now, horizon_days=30)
    v = result.value
    _row("önümüzdeki maç", v.upcoming_count)
    _row("7 günde / 14 günde", f"{v.matches_next_7d} / {v.matches_next_14d}")
    _row("ilk maça kalan", f"{v.days_until_next_match} gün" if v.days_until_next_match else "—")
    _row("yoğun fikstür", "evet" if v.dense_schedule else "hayır")
    if v.next_kickoffs:
        _row("en yakın 3 kickoff", ", ".join(v.next_kickoffs[:3]))
    if com is not None:
        print()
        print("  AI yorumu:")
        print("    " + com.explain(result).replace("\n", "\n    "))


def _show_matchup(home: int, away: int, *, com: ClaudeCommentator | None) -> None:
    from sqlalchemy import or_, select

    from app.db import models

    if home == away:
        print(f"[skip] matchup: aynı takım id'si {home}")
        return

    def _team_matches(team_id: int):
        with SessionLocal() as s:
            return list(
                s.execute(
                    select(models.Match)
                    .where(
                        models.Match.sport == football.SPORT_NAME,
                        or_(
                            models.Match.home_team_external_id == team_id,
                            models.Match.away_team_external_id == team_id,
                        ),
                    )
                    .order_by(models.Match.kickoff.desc())
                ).scalars()
            )

    home_matches = _team_matches(home)
    away_matches = _team_matches(away)
    _hr(f"Matchup raporu — {home} (ev) vs {away} (dep)")
    if not home_matches or not away_matches:
        print("  (taraflardan birinin maçı yok)")
        return

    home_form = compute_form(home, home_matches, last_n=5)
    away_form = compute_form(away, away_matches, last_n=5)
    with SessionLocal() as s:
        h2h_matches = list(
            s.execute(
                select(models.Match).where(
                    models.Match.sport == football.SPORT_NAME,
                    or_(
                        (models.Match.home_team_external_id == home)
                        & (models.Match.away_team_external_id == away),
                        (models.Match.home_team_external_id == away)
                        & (models.Match.away_team_external_id == home),
                    ),
                )
            ).scalars()
        )
    h2h = compute_head_to_head(home, away, h2h_matches)

    result = compute_matchup(
        home_form.value, away_form.value, h2h.value,
        home_team_id=home, away_team_id=away,
    )
    v = result.value
    _row("form farkı (ppg)", f"{v.form_delta_ppg:+}")
    _row("form farkı (gd/maç)", f"{v.form_delta_goal_diff:+}")
    _row("momentum farkı", f"{v.momentum_delta:+}")
    _row("clean sheet farkı", f"{v.clean_sheets_delta:+d}")
    _row("ev sahibi avantaj %", f"{int(v.home_advantage_factor * 100)}")
    _row("H2H baskınlık", f"{v.h2h_dominance:+.1f}")
    _row("advantage_score", f"{v.advantage_score:+}")
    if com is not None:
        print()
        print("  AI yorumu:")
        print("    " + com.explain(result).replace("\n", "\n    "))


def _show_predict(match_id: int, *, com: ClaudeCommentator | None) -> None:
    from sqlalchemy import or_, select

    from app.db import models

    with SessionLocal() as s:
        match = s.execute(
            select(models.Match).where(
                models.Match.sport == football.SPORT_NAME,
                models.Match.external_id == match_id,
            )
        ).scalar_one_or_none()
        if match is None:
            print(f"[skip] match {match_id} yok (predict)")
            return
        home_id = match.home_team_external_id
        away_id = match.away_team_external_id

        def _prior(team_id: int):
            return list(
                s.execute(
                    select(models.Match)
                    .where(
                        models.Match.sport == football.SPORT_NAME,
                        models.Match.kickoff < match.kickoff,
                        or_(
                            models.Match.home_team_external_id == team_id,
                            models.Match.away_team_external_id == team_id,
                        ),
                    )
                    .order_by(models.Match.kickoff.desc())
                ).scalars()
            )

        home_matches = _prior(home_id)
        away_matches = _prior(away_id)

    home_form = compute_form(home_id, home_matches, last_n=5).value
    away_form = compute_form(away_id, away_matches, last_n=5).value
    result = compute_predict(
        home_form, away_form, home_team_id=home_id, away_team_id=away_id,
    )
    v = result.value
    _hr(f"Skor tahmini — match_id={match_id} ({home_id} vs {away_id})")
    _row("beklenen goller", f"ev {v.expected_home_goals} – dep {v.expected_away_goals}")
    _row("1X2 (%)", f"ev {int(v.prob_home_win * 100)} / X {int(v.prob_draw * 100)} / dep {int(v.prob_away_win * 100)}")
    _row("en olası skor", f"{v.most_likely_score[0]}-{v.most_likely_score[1]} (P=%{v.most_likely_score_prob * 100:.1f})")
    _row("model", "Poisson + DC" if v.rho_used != 0.0 else "saf Poisson")
    if v.low_confidence:
        _row("UYARI", f"örneklem küçük ({v.sample_size} maç), güven DÜŞÜK")
    if com is not None:
        print()
        print("  AI yorumu:")
        print("    " + com.explain(result).replace("\n", "\n    "))


def _show_fixture_difficulty(team_id: int, *, com: ClaudeCommentator | None) -> None:
    from datetime import datetime, timedelta  # noqa: E402

    from sqlalchemy import or_, select

    from app.db import models

    def _team_matches(s, t_id: int):
        return list(
            s.execute(
                select(models.Match)
                .where(
                    models.Match.sport == football.SPORT_NAME,
                    or_(
                        models.Match.home_team_external_id == t_id,
                        models.Match.away_team_external_id == t_id,
                    ),
                )
                .order_by(models.Match.kickoff.desc())
            ).scalars()
        )

    with SessionLocal() as s:
        matches = _team_matches(s, team_id)
        if not matches:
            _hr(f"Fikstür zorluğu — takım {team_id}")
            print("  (maç yok)")
            return
        # SQLite tz-strip + horizon
        ref_tz = matches[0].kickoff.tzinfo
        now = datetime.now(ref_tz)
        horizon = now + timedelta(days=30)
        upcoming_opps = {
            (m.away_team_external_id if m.home_team_external_id == team_id else m.home_team_external_id)
            for m in matches
            if m.kickoff > now and m.kickoff <= horizon
            and m.status not in football.FINISHED_STATUSES
        }
        ratings: dict[int, float] = {}
        for opp in upcoming_opps:
            opp_matches = _team_matches(s, opp)
            if not opp_matches:
                continue
            rr = compute_team_rating(opp, opp_matches, last_n=10).value
            if rr.matches_considered > 0:
                ratings[opp] = rr.rating

    horizon_matches = [m for m in matches if m.kickoff <= horizon]
    result = compute_fixture_difficulty(team_id, horizon_matches, ratings, now=now)
    v = result.value
    _hr(f"Fikstür zorluğu — takım {team_id} (next 30 gün)")
    _row("ratingi bilinen maç", v.matches_considered)
    _row("rating'i bilinmeyen", v.matches_unknown_opponent)
    if v.matches_considered > 0:
        _row("ortalama rakip rating", v.avg_opponent_rating)
        _row("zaman ağırlıklı zorluk", v.weighted_difficulty)
        _row("en zor rakip", f"{v.hardest_opponent_id} (rating {v.hardest_opponent_rating})")
        _row("en kolay rakip", f"{v.easiest_opponent_id} (rating {v.easiest_opponent_rating})")
        _row("ev/dep dağılımı", f"{v.home_match_count} ev / {v.away_match_count} dep")
    if com is not None:
        print()
        print("  AI yorumu:")
        print("    " + com.explain(result).replace("\n", "\n    "))


def main() -> None:
    parser = argparse.ArgumentParser(description="football-intelligence end-to-end demo")
    parser.add_argument("--league", type=int, default=203, help="API-Football league.id (fixture varsa)")
    parser.add_argument("--season", type=int, default=2024)
    parser.add_argument("--reset", action="store_true", help="DB'yi sıfırla (yalnız SQLite)")
    parser.add_argument("--team", type=int, default=611, help="Analiz edilecek takım")
    parser.add_argument("--vs", type=int, default=607, help="Head-to-head karşılaştırılacak takım")
    parser.add_argument("--match", type=int, default=1234140, help="Preview için maç external_id (NS olan ideal)")
    args = parser.parse_args()

    _maybe_reset(args.reset)
    _alembic_check()
    _run_sync(args.league, args.season)
    _print_db_stats()

    client = AnthropicClient()
    com: ClaudeCommentator | None = None
    if client.is_stub():
        print()
        print("[bilgi] ANTHROPIC_API_KEY yok — AI yorumları atlandı (stub'lar gösterilmedi).")
    else:
        com = ClaudeCommentator(client=client)
        print()
        print("[bilgi] ANTHROPIC_API_KEY var — Claude yorumları dahil.")

    _show_team_analysis(args.team, com=com)
    _show_schedule(args.team, com=com)
    _show_fixture_difficulty(args.team, com=com)
    _show_h2h(args.team, args.vs, com=com)
    _show_matchup(args.team, args.vs, com=com)
    _show_preview(args.match, com=com)
    _show_predict(args.match, com=com)

    _hr("Demo tamam")
    print("  Sıradakiler:")
    print("  - python scripts/run_job.py sync_league --league 203 --season 2024")
    print("  - uvicorn app.api.main:app --reload  (sonra: curl -H 'X-API-Key: ...' .../admin/db-stats)")
    print()


if __name__ == "__main__":
    main()
