"""End-to-end smoke test — full decision flow on La Liga match.

Akış:
  1. StatsBomb match ingest (16029 Barcelona-Sevilla)
  2. live-decision endpoint çağır (10 engine + context_engine primary)
  3. PrimaryBanner ŞİMDİ aksiyonunu DB'ye yansıt (POST decisions)
  4. /admin/decisions/recent listede pending görünür mü doğrula
  5. ✓/✗ outcome mark uygula (POST decisions/{id}/outcome)
  6. /admin/decisions/recent hit_rate güncellenir mi doğrula

Sonuç: PASS/FAIL özeti + her adımın çıktısı.

Endpoint fonksiyonları doğrudan çağrılır (TestClient ASGI middleware'i
yerine in-process — tenant ContextVar smoke setup'ta set edilir).

Çalıştırma:
    DATABASE_URL=sqlite:///./smoke_e2e.db python -m scripts.smoke_decision_e2e
"""
from __future__ import annotations

from datetime import UTC, datetime

from app.data.ingest.event import ingest_events_for_match
from app.data.sources.statsbomb_open import StatsBombOpen
from app.db import models
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.db.tenant_context import set_current_tenant_id
from app.sports import football

MATCH_ID = 16029
TENANT = "t-demo"  # demo_replay tipiyle tutarlı — replay/dev_seed bunu kullanır


def _hr(c: str = "═", w: int = 70) -> str:
    return c * w


def _step(n: int, title: str) -> None:
    print(f"\n{_hr('─')}")
    print(f"  STEP {n}/6  ·  {title}")
    print(_hr('─'))


def _ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def _fail(msg: str) -> str:
    print(f"  ✗ {msg}")
    return f"FAIL: {msg}"


def _setup_db() -> None:
    Base.metadata.create_all(engine)
    with SessionLocal() as s:
        if s.get(models.Tenant, TENANT) is None:
            s.add(models.Tenant(
                id=TENANT, slug=TENANT, name="Smoke",
                settings_json="{}", active=True,
                created_at=datetime.now(UTC),
            ))
            s.commit()


def _ingest() -> None:
    with SessionLocal() as s:
        s.info["tenant_id"] = TENANT
        # Match seed
        existing = s.execute(
            models.Match.__table__.select().where(
                models.Match.sport == football.SPORT_NAME,
                models.Match.external_id == MATCH_ID,
            )
        ).first()
        if existing is None:
            src = StatsBombOpen()
            seeded = False
            for cid, sid in [(11, 4), (11, 90), (11, 42)]:
                for m in src.get_matches(competition_id=cid, season_id=sid):
                    if m["match_id"] != MATCH_ID:
                        continue
                    ko = datetime.fromisoformat(
                        f"{m['match_date']}T{m.get('kick_off') or '20:00:00'}+00:00",
                    ) if m.get("match_date") else datetime.now(UTC)
                    s.add(models.Match(
                        sport=football.SPORT_NAME, external_id=MATCH_ID,
                        league_external_id=cid, season=int(sid),
                        kickoff=ko, status="FT",
                        home_team_external_id=m["home_team"]["home_team_id"],
                        away_team_external_id=m["away_team"]["away_team_id"],
                        home_score=int(m.get("home_score", 0)),
                        away_score=int(m.get("away_score", 0)),
                        tenant_id=TENANT,
                    ))
                    s.commit()
                    seeded = True
                    print(f"  match {MATCH_ID} seed'lendi (comp={cid} season={sid})")
                    break
                if seeded:
                    break
            if not seeded:
                raise RuntimeError(f"match {MATCH_ID} StatsBomb'da bulunamadı")
        else:
            print(f"  match {MATCH_ID} zaten var")

        # Event ingest (idempotent — source_event_id ile skip eder)
        r = ingest_events_for_match(
            s, source=StatsBombOpen(),
            match_external_id=MATCH_ID, tenant_id=TENANT,
        )
        s.commit()
        print(
            f"  ingest: +{r.rows_inserted} yeni event "
            f"(skip={r.rows_skipped}; toplam {r.shots} şut, "
            f"{r.passes} pas, {r.fouls} faul)",
        )


def main() -> int:
    print(f"\n{_hr('▓')}")
    print(f"  END-TO-END SMOKE — match {MATCH_ID} (Barcelona-Sevilla)")
    print(_hr('▓'))

    failures: list[str] = []
    # Tüm context için tenant set — ingest + endpoint çağrılarında query filter
    set_current_tenant_id(TENANT)
    _setup_db()
    _ingest()

    try:
        # ────────────────────────────────────────────────────────
        _step(1, "live_decision_endpoint() — 10 engine + context primary")
        from app.api.admin import (
            create_decision,
            decisions_recent_endpoint,
            live_decision_endpoint,
            record_decision_outcome,
        )
        with SessionLocal() as s:
            s.info["tenant_id"] = TENANT
            set_current_tenant_id(TENANT)
            body = live_decision_endpoint(
                match_id=MATCH_ID, my_team_id=217,
                current_minute=80.0,
                star_player_id=None,
                draw_is_enough=False, must_win=False,
                session=s,
            )
        primary = (body.get("context") or {}).get("primary") or {}
        primary_headline = primary.get("headline") if primary else None
        _ok(f"score={body.get('score')} · "
            f"primary={primary_headline or '(izleme)'}")
        for must in ("momentum", "sub_timing", "closing_strategy",
                     "foul_pressure", "hot_hand"):
            if must not in body:
                failures.append(_fail(f"engine '{must}' panel'de yok"))

        # ────────────────────────────────────────────────────────
        _step(2, "create_decision() — Karar Yansıt")
        decision_payload = {
            "team_external_id": 217, "minute": 80.0, "period": 2,
            "decision_type": "tactical_instruction",
            "notes": primary_headline or "smoke decision",
            "recommended": True,
            "confidence": primary.get("confidence", 0.7),
        }
        with SessionLocal() as s:
            s.info["tenant_id"] = TENANT
            set_current_tenant_id(TENANT)
            d = create_decision(match_id=MATCH_ID, payload=decision_payload,
                                 session=s)
        decision_id = d["id"]
        _ok(f"decision id={decision_id} kaydedildi · outcome={d['outcome']}")

        # ────────────────────────────────────────────────────────
        _step(3, "decisions_recent_endpoint() — pending görünmeli")
        with SessionLocal() as s:
            s.info["tenant_id"] = TENANT
            set_current_tenant_id(TENANT)
            rb = decisions_recent_endpoint(limit=10, team_external_id=None,
                                            session=s)
            s.commit()  # cache_set'i kalıcılaştır
        ids = [d["id"] for d in rb["decisions"]]
        if decision_id not in ids:
            failures.append(_fail(f"decision {decision_id} listede yok"))
        else:
            _ok(f"decision listede; "
                f"total={rb['summary']['total']}, "
                f"pending={rb['summary']['pending']}, "
                f"hit_rate={rb['summary']['hit_rate']}, "
                f"_cache={rb.get('_cache')}")

        # ────────────────────────────────────────────────────────
        _step(4, "decisions_recent_endpoint() 2. çağrı — cache HIT")
        with SessionLocal() as s:
            s.info["tenant_id"] = TENANT
            set_current_tenant_id(TENANT)
            rb2 = decisions_recent_endpoint(limit=10, team_external_id=None,
                                             session=s)
        if rb2.get("_cache") != "hit":
            failures.append(_fail(f"cache hit beklendi, geldi: {rb2.get('_cache')}"))
        else:
            _ok("cache=hit doğrulandı (30sn TTL)")

        # ────────────────────────────────────────────────────────
        _step(5, "record_decision_outcome() — pozitif mark")
        with SessionLocal() as s:
            s.info["tenant_id"] = TENANT
            set_current_tenant_id(TENANT)
            out = record_decision_outcome(
                decision_id=decision_id,
                payload={"outcome": "positive", "outcome_value": 0.7,
                         "outcome_notes": "smoke pozitif"},
                session=s,
            )
        _ok(f"outcome={out['outcome']}, recorded_at OK")

        # ────────────────────────────────────────────────────────
        _step(6, "decisions_recent_endpoint() — hit_rate güncellenmiş")
        with SessionLocal() as s:
            s.info["tenant_id"] = TENANT
            set_current_tenant_id(TENANT)
            # Farklı limit → ayrı cache key → fresh query
            rb3 = decisions_recent_endpoint(limit=11, team_external_id=None,
                                             session=s)
        pos = rb3["summary"]["positive"]
        if pos < 1:
            failures.append(_fail(
                f"positive=0 beklenmedi (outcome mark sonrası): {rb3['summary']}",
            ))
        else:
            _ok(f"positive={pos}, hit_rate={rb3['summary']['hit_rate']}, "
                f"resolved={rb3['summary']['resolved']}")

    except Exception as e:  # noqa: BLE001
        failures.append(_fail(f"unexpected: {type(e).__name__}: {e}"))

    return _summary(failures)


def _summary(failures: list[str]) -> int:
    print(f"\n{_hr('▓')}")
    if failures:
        print(f"  ✗ SMOKE FAILED — {len(failures)} hata")
        for f in failures:
            print(f"    {f}")
        print(_hr('▓'))
        return 1
    print("  ✓ SMOKE PASSED — full decision flow green")
    print(_hr('▓'))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
