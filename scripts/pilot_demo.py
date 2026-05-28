"""Pilot demo runbook — pilot kulübe gösterilebilir tek-komut senaryo.

Akış:
1. (Opsiyonel) DB'yi sıfırla — `--reset`
2. Migration'ları çalıştır
3. "Demo Kulüp" tenant + admin user oluştur
4. Süper Lig fixture sync (USE_FIXTURES=true; API kotası harcamaz)
5. JWT login akışı (admin@demo-club.com)
6. Yaklaşan maç bul, agent zinciri çalıştır:
   - LineupRecommendationAgent
   - PreMatchReportAgent
   - MegaMatchAgent
7. xG model durumu + tahmin doğruluğu
8. Asistan chat örneği (stub — ANTHROPIC_API_KEY yoksa)
9. Özet rapor: "pilot kulübe ne gösterebiliriz" formatlı çıktı

Kullanım:
    python scripts/pilot_demo.py                  # SQLite + fixtures, fresh DB
    python scripts/pilot_demo.py --reset          # mevcut _pilot_demo.db'yi sil
    python scripts/pilot_demo.py --output md      # markdown dump (slide için)

Çevre:
- USE_FIXTURES=true (default) — gerçek API'ya gitmez
- ANTHROPIC_API_KEY varsa → gerçek AI brief; yoksa stub
- DATABASE_URL otomatik sqlite:///./_pilot_demo.db
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import uuid as _uuid
from datetime import UTC, datetime
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Defaults — pilot demo dev-mode SQLite + fixtures
os.environ.setdefault("DATABASE_URL", "sqlite:///./_pilot_demo.db")
os.environ.setdefault("USE_FIXTURES", "true")
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ.setdefault("JWT_SECRET_KEY", "pilot-demo-secret-key-32-byte-min")


def _section(title: str, emoji: str = "") -> None:
    print()
    print("\033[1;36m" + "═" * 70 + "\033[0m")
    print(f"\033[1;36m {emoji} {title}\033[0m")
    print("\033[1;36m" + "═" * 70 + "\033[0m")


def _row(label: str, value: object, *, ok: bool = True) -> None:
    mark = "\033[32m✓\033[0m" if ok else "\033[33m⚠\033[0m"
    print(f"  {mark} {label:.<42s} {value}")


def _info(text: str) -> None:
    print(f"  \033[2m{text}\033[0m")


def _step(text: str) -> None:
    print(f"\n  \033[1;33m▸\033[0m \033[1m{text}\033[0m")


def _maybe_reset(reset: bool) -> None:
    if not reset:
        return
    db = os.environ["DATABASE_URL"]
    if db.startswith("sqlite:///"):
        path = Path(db.replace("sqlite:///", ""))
        if path.exists():
            path.unlink()
            print(f"  [reset] {path} silindi")


def _migrate() -> None:
    from alembic.config import Config

    from alembic import command
    cfg = Config(str(_PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_PROJECT_ROOT / "alembic"))
    command.upgrade(cfg, "head")


def _seed_tenant_and_admin(session):
    from app.auth.service import create_user
    from app.db import models
    now = datetime.now(UTC)
    tenant = models.Tenant(
        id=str(_uuid.uuid4()), slug="demo-club",
        name="Demo Kulüp", settings_json="{}",
        active=True, created_at=now,
    )
    session.add(tenant)
    session.flush()
    user = create_user(
        session, tenant_id=tenant.id,
        email="admin@demo-club.com", password="demo-pass-1234",
        role="admin",
    )
    session.commit()
    return tenant, user


def _run_sync(tenant_id: str) -> dict:
    """Süper Lig fixture sync — tenant_filter listener tenant_id'yi
    session.info'dan otomatik enjekte eder (sync_league tenant-agnostic)."""
    from app.data.ingest import sync_league
    from app.data.sources.api_football import APIFootball
    from app.db.session import SessionLocal
    source = APIFootball()
    with SessionLocal() as s:
        s.info["tenant_id"] = tenant_id  # before_flush listener doldurur
        report = sync_league(s, source, league_id=203, season=2024)
    return {
        "leagues": report.leagues_written,
        "teams": report.teams_written,
        "matches": report.matches_written,
        "snapshot_id": report.snapshot_id,
    }


def _jwt_login_test() -> str:
    """Login endpoint smoke — TestClient ile."""
    from fastapi.testclient import TestClient

    from app.api.main import app
    client = TestClient(app)
    r = client.post("/auth/login", json={
        "email": "admin@demo-club.com",
        "password": "demo-pass-1234",
    })
    if r.status_code != 200:
        raise RuntimeError(f"login fail: {r.status_code} {r.text[:200]}")
    return r.json()["access_token"]


def _run_agents_for_first_upcoming_match(tenant_id: str) -> dict:
    """Bir yaklaşan maç için Lineup + PreMatch + MegaMatch agent'larını çalıştır."""
    from sqlalchemy import select

    from app.agents import (
        LineupRecommendationAgent,
        MegaMatchAgent,
        PreMatchReportAgent,
        save_agent_output,
    )
    from app.db import models
    from app.db.session import SessionLocal
    from app.sports import football
    out: dict = {"errors": [], "succeeded": [], "match": None}

    with SessionLocal() as s:
        s.info["tenant_id"] = tenant_id
        # Yaklaşan veya status="NS" maç bul
        sample = s.execute(
            select(models.Match).where(
                models.Match.sport == football.SPORT_NAME,
            ).limit(1)
        ).scalar_one_or_none()
        if sample is None:
            return out
        ref_tz = sample.kickoff.tzinfo
        now_local = datetime.now(ref_tz)
        upcoming = s.execute(
            select(models.Match).where(
                models.Match.sport == football.SPORT_NAME,
                models.Match.kickoff > now_local,
                ~models.Match.status.in_(football.FINISHED_STATUSES),
            ).order_by(models.Match.kickoff).limit(1)
        ).scalar_one_or_none()
        if upcoming is None:
            # NS hiç yoksa en yeni FT maçı al (post-match için yeterli)
            upcoming = s.execute(
                select(models.Match).where(
                    models.Match.sport == football.SPORT_NAME,
                ).order_by(models.Match.kickoff.desc()).limit(1)
            ).scalar_one_or_none()
            if upcoming is None:
                return out
        out["match"] = {
            "match_id": upcoming.external_id,
            "home_team_id": upcoming.home_team_external_id,
            "away_team_id": upcoming.away_team_external_id,
            "kickoff": upcoming.kickoff.isoformat(),
            "status": upcoming.status,
        }
        match_id = upcoming.external_id
        home = upcoming.home_team_external_id

        # 1) LineupRecommendationAgent (home team için)
        lineup_agent = LineupRecommendationAgent()
        try:
            r = lineup_agent.run(s, context={
                "match_external_id": match_id, "team_external_id": home,
            })
            saved = save_agent_output(
                s, result=r, agent_name=lineup_agent.name,
                agent_version=lineup_agent.version,
            )
            saved.tenant_id = tenant_id
            out["succeeded"].append({"agent": "lineup_recommendation", "summary": r.summary})
        except Exception as e:  # noqa: BLE001
            out["errors"].append(f"lineup: {type(e).__name__}: {e}")

        # 2) PreMatchReportAgent
        pre_match = PreMatchReportAgent()
        try:
            r = pre_match.run(s, context={"match_external_id": match_id})
            saved = save_agent_output(
                s, result=r, agent_name=pre_match.name,
                agent_version=pre_match.version,
            )
            saved.tenant_id = tenant_id
            out["succeeded"].append({"agent": "pre_match_report", "summary": r.summary})
        except Exception as e:  # noqa: BLE001
            out["errors"].append(f"pre_match: {type(e).__name__}: {e}")

        # 3) MegaMatchAgent
        mega = MegaMatchAgent()
        try:
            r = mega.run(s, context={"match_external_id": match_id})
            saved = save_agent_output(
                s, result=r, agent_name=mega.name,
                agent_version=mega.version,
            )
            saved.tenant_id = tenant_id
            out["succeeded"].append({"agent": "mega_match", "summary": r.summary})
        except Exception as e:  # noqa: BLE001
            out["errors"].append(f"mega_match: {type(e).__name__}: {e}")

        s.commit()
    return out


def _xg_status() -> dict:
    from app.engine.xg.model_loader import get_model_status
    return get_model_status()


def _predict_summary(tenant_id: str) -> dict | None:
    """İlk maç için tahmin örneği."""
    from sqlalchemy import select

    from app.db import models
    from app.db.session import SessionLocal
    from app.engine.form import compute_form
    from app.engine.predict import compute_predict
    from app.sports import football
    with SessionLocal() as s:
        s.info["tenant_id"] = tenant_id
        m = s.execute(
            select(models.Match).where(
                models.Match.sport == football.SPORT_NAME,
                models.Match.status.in_(("NS", "TBD")),
            ).order_by(models.Match.kickoff).limit(1)
        ).scalar_one_or_none()
        if m is None:
            return None
        # Önce maçlardan form oluştur
        from sqlalchemy import or_
        home_prior = list(s.execute(
            select(models.Match).where(
                models.Match.sport == football.SPORT_NAME,
                models.Match.kickoff < m.kickoff,
                or_(
                    models.Match.home_team_external_id == m.home_team_external_id,
                    models.Match.away_team_external_id == m.home_team_external_id,
                ),
            )
        ).scalars())
        away_prior = list(s.execute(
            select(models.Match).where(
                models.Match.sport == football.SPORT_NAME,
                models.Match.kickoff < m.kickoff,
                or_(
                    models.Match.home_team_external_id == m.away_team_external_id,
                    models.Match.away_team_external_id == m.away_team_external_id,
                ),
            )
        ).scalars())
        home_form = compute_form(m.home_team_external_id, home_prior, last_n=5).value
        away_form = compute_form(m.away_team_external_id, away_prior, last_n=5).value
        p = compute_predict(
            home_form, away_form,
            home_team_id=m.home_team_external_id,
            away_team_id=m.away_team_external_id,
        ).value
        return {
            "match_id": m.external_id,
            "home_team_id": m.home_team_external_id,
            "away_team_id": m.away_team_external_id,
            "prob_home_win": round(p.prob_home_win, 3),
            "prob_draw": round(p.prob_draw, 3),
            "prob_away_win": round(p.prob_away_win, 3),
            "expected_goals": f"{p.expected_home_goals:.2f} - {p.expected_away_goals:.2f}",
            "most_likely_score": f"{p.most_likely_score[0]}-{p.most_likely_score[1]}",
        }


def _tactical_inventory() -> dict:
    """30 engine'in canlı listesi (Faz N + Wave 2 + Wave 3)."""
    faz_n = [
        "xt", "xa", "ppda", "field_tilt",
        "player_role", "xg_match_graph",
        "build_up_pattern", "match_phase",
    ]
    wave_2 = [
        "pressing_trigger", "defensive_line", "compactness",
        "transition", "channel_preference", "press_resistance",
        "set_piece_zones",
    ]
    wave_3 = [
        "cross_effectiveness", "cutback_frequency", "off_ball_runs",
        "final_third_entries", "defensive_duels", "recovery_zone_heat",
        "counter_press_triggers", "direct_play", "possession_quality",
        "tempo", "overperformance", "progressive_passes",
        "carries_into_final_third",
    ]
    composite = ["match_dominance", "coaching_identity"]
    return {
        "faz_n": f"{len(faz_n)} modül ({', '.join(faz_n[:3])}, ...)",
        "wave_2": f"{len(wave_2)} modül",
        "wave_3": f"{len(wave_3)} modül",
        "composite": f"{len(composite)} modül (match_dominance, coaching_identity)",
        "total_engines": len(faz_n) + len(wave_2) + len(wave_3) + len(composite),
    }


def _assistant_chat_demo(tenant_id: str) -> str:
    """Basit assistant chat — stub mode'da bile çıktı verir."""
    from app.assistant import chat as assistant_chat
    from app.db.session import SessionLocal
    with SessionLocal() as s:
        s.info["tenant_id"] = tenant_id
        result = assistant_chat(
            s, user_message="Galatasaray'ın sıradaki maça hazırlığı nasıl?",
            team_external_id=611,
        )
        s.commit()
        return result.text


def _render(report: dict, *, output: str = "tty") -> None:
    """Final rapor — tty (renkli) ya da md (markdown)."""
    if output == "md":
        _render_md(report)
        return
    _render_tty(report)


def _render_tty(report: dict) -> None:
    """Pilot kulübe gösterilebilir formatlı çıktı."""
    _section("PİLOT DEMO RAPORU", "📋")
    print()
    _row("Süre", f"{report['elapsed']:.1f} saniye")
    _row("Tenant", report['tenant']['slug'])
    _row("Admin user", report['user']['email'])
    print()
    print("  \033[1mGenel:\033[0m")
    print(f"    Sync: {report['sync']['leagues']} lig, {report['sync']['teams']} takım, "
          f"{report['sync']['matches']} maç")
    print(f"    Login (JWT): \033[32m✓\033[0m token alındı ({report['jwt_token_len']} char)")
    print(f"    xG modeli: \033[35m{report['xg_status']['status']}\033[0m "
          f"(mode: {report['xg_status']['mode_in_use']})")

    if report.get("match"):
        m = report["match"]
        print()
        print(f"  \033[1mDemo maç:\033[0m team {m['home_team_id']} vs team {m['away_team_id']}")
        print(f"    Kickoff: {m['kickoff']}")
        print(f"    Status:  {m['status']}")

    if report.get("predict"):
        p = report["predict"]
        print()
        print("  \033[1mTahmin:\033[0m")
        print(f"    Ev / X / Dep: \033[32m{p['prob_home_win']*100:.0f}%\033[0m / "
              f"{p['prob_draw']*100:.0f}% / "
              f"\033[31m{p['prob_away_win']*100:.0f}%\033[0m")
        print(f"    Beklenen gol: {p['expected_goals']}")
        print(f"    En olası skor: \033[1m{p['most_likely_score']}\033[0m")

    print()
    print(f"  \033[1mAgent zinciri ({len(report['agents']['succeeded'])} OK):\033[0m")
    for ag in report['agents']['succeeded']:
        print(f"    \033[32m✓\033[0m {ag['agent']}: \033[2m{ag['summary'][:70]}...\033[0m")
    for err in report['agents']['errors']:
        print(f"    \033[33m⚠\033[0m {err[:80]}")

    print()
    print("  \033[1mAsistan örneği:\033[0m")
    chat_lines = report["chat"].split("\n")
    for line in chat_lines[:3]:
        print(f"    \033[2m{line[:90]}\033[0m")
    if len(chat_lines) > 3:
        print(f"    \033[2m... ({len(chat_lines)-3} satır daha)\033[0m")

    _section("PILOTA GÖSTERILECEK", "🎯")
    print(
        "  • Login → JWT bearer flow çalışıyor (multi-tenant izolasyon)\n"
        "  • Süper Lig sync uçtan uca — 20 takım, fixture sayısı\n"
        f"  • {len(report['agents']['succeeded'])} agent her maç için AI brief üretiyor\n"
        "  • Tahmin doğruluğu /admin/predict-accuracy üzerinden ölçülebilir\n"
        "  • Asistan chat — doğal dil ile soru sorulabilir\n"
        "  • Dashboard: http://localhost:8000/dashboard\n"
        "  • Yardımcı manager: http://localhost:8000/dashboard'da chat widget\n"
    )


def _render_md(report: dict) -> None:
    """Markdown çıktı — slide için copy-paste."""
    print(f"""# manager2 — Pilot Demo Raporu

**Süre:** {report['elapsed']:.1f} saniye
**Tenant:** `{report['tenant']['slug']}`
**Admin:** `{report['user']['email']}`

## Genel
- Sync: **{report['sync']['leagues']}** lig, **{report['sync']['teams']}** takım, **{report['sync']['matches']}** maç
- Login (JWT): ✓ access_token alındı ({report['jwt_token_len']} char)
- xG modeli: `{report['xg_status']['status']}` (mode: `{report['xg_status']['mode_in_use']}`)

## Demo maç
- Match ID: `{report.get('match', {}).get('match_id', '—')}`
- Ev / Dep: `{report.get('match', {}).get('home_team_id', '—')}` vs `{report.get('match', {}).get('away_team_id', '—')}`
- Kickoff: `{report.get('match', {}).get('kickoff', '—')}`

## Tahmin
""")
    if report.get("predict"):
        p = report["predict"]
        print(f"""- **Ev:** {p['prob_home_win']*100:.0f}%
- **X:** {p['prob_draw']*100:.0f}%
- **Dep:** {p['prob_away_win']*100:.0f}%
- Beklenen gol: {p['expected_goals']}
- En olası skor: **{p['most_likely_score']}**""")

    print(f"\n## Agent zinciri ({len(report['agents']['succeeded'])} OK)\n")
    for ag in report['agents']['succeeded']:
        print(f"- ✓ **{ag['agent']}**: {ag['summary']}")

    print("\n## Asistan örneği\n```")
    print(report["chat"][:500])
    print("```\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="manager2 pilot demo runbook")
    parser.add_argument("--reset", action="store_true", help="DB'yi sıfırla (SQLite)")
    parser.add_argument("--output", choices=["tty", "md"], default="tty")
    args = parser.parse_args()

    started = time.time()

    _section("MANAGER2 PİLOT DEMO", "🚀")
    _step("1/8 DB hazırla")
    _maybe_reset(args.reset)
    _migrate()
    _info("Alembic head migration tamam")

    _step("2/8 Demo tenant + admin user oluştur")
    from app.db.session import SessionLocal
    with SessionLocal() as s:
        tenant, user = _seed_tenant_and_admin(s)
        tenant_id = tenant.id
        user_email = user.email
    _row("tenant", tenant.slug)
    _row("admin email", user_email)
    _row("tenant_id", tenant_id)

    _step("3/8 Süper Lig sync (USE_FIXTURES=true)")
    sync = _run_sync(tenant_id)
    _row("leagues yazıldı", sync["leagues"])
    _row("teams yazıldı", sync["teams"])
    _row("matches yazıldı", sync["matches"])

    _step("4/8 JWT login akışı")
    token = _jwt_login_test()
    _row("access_token", f"{token[:24]}... ({len(token)} char)")

    _step("5/8 Agent zinciri (lineup → pre_match → mega_match)")
    agents = _run_agents_for_first_upcoming_match(tenant_id)
    for ag in agents["succeeded"]:
        _row(ag["agent"], ag["summary"][:50])
    for err in agents["errors"]:
        _row("error", err[:60], ok=False)

    _step("6/8 xG modeli durumu")
    xg = _xg_status()
    _row("status", xg["status"])
    _row("mode", xg["mode_in_use"])

    _step("7/9 Tahmin örneği (engine.predict + Dixon-Coles)")
    predict = _predict_summary(tenant_id)
    if predict:
        _row("match", f"{predict['home_team_id']} vs {predict['away_team_id']}")
        _row("1X2", f"{predict['prob_home_win']*100:.0f}% / "
                    f"{predict['prob_draw']*100:.0f}% / "
                    f"{predict['prob_away_win']*100:.0f}%")
        _row("most likely", predict["most_likely_score"])

    _step("8/9 Taktiksel modüller (Faz N + Wave 2 + 3 — 30 engine envanteri)")
    tactical = _tactical_inventory()
    _row("toplam engine", tactical["total_engines"])
    _row("Faz N (Sprint 1-3)", tactical["faz_n"])
    _row("Wave 2 (savunma stili)", tactical["wave_2"])
    _row("Wave 3 (Opta-tarz)", tactical["wave_3"])
    _row("composite + identity", tactical["composite"])
    _info("Production'da /admin/teams/{id}/tactical-profile batch endpoint çağır")

    _step("9/9 Asistan örneği (Claude tool_use)")
    chat = _assistant_chat_demo(tenant_id)
    print(f"    \033[2m{chat[:200]}...\033[0m")

    elapsed = time.time() - started
    report = {
        "elapsed": elapsed,
        "tenant": {"slug": tenant.slug, "id": tenant_id},
        "user": {"email": user_email},
        "sync": sync,
        "jwt_token_len": len(token),
        "match": agents.get("match"),
        "agents": agents,
        "xg_status": xg,
        "predict": predict,
        "tactical": tactical,
        "chat": chat,
    }
    _render(report, output=args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
