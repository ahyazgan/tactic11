"""E2E smoke test — yeni 8 tactical/performance endpoint'i + agent v2/v3.

Çalıştırma:
    DATABASE_URL=sqlite:///./_smoke.db USE_FIXTURES=true \\
    JWT_SECRET_KEY='smoke-secret-key-32-byte-minimum-long' APP_ENV=dev \\
    python scripts/e2e_smoke_tactical.py

Yaptıkları:
  1. Tenant + admin user seed
  2. Yeni 8 endpoint'i in-process TestClient ile vurur, yanıt + status kontrol
  3. TacticalAdjustmentAgent v3 + PreMatchReportAgent v2 — output_json'da
     match_plan field'larını doğrular
  4. Konsol özet

Bağımlılık: alembic upgrade head önceden çalıştırılmış olmalı.
"""
from __future__ import annotations

import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite:///./_smoke.db")
os.environ.setdefault("USE_FIXTURES", "true")
os.environ.setdefault("JWT_SECRET_KEY", "smoke-secret-key-32-byte-minimum-long")
os.environ.setdefault("APP_ENV", "dev")

from contextlib import suppress  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.agents import PreMatchReportAgent, TacticalAdjustmentAgent  # noqa: E402
from app.ai import AnthropicClient, ClaudeCommentator  # noqa: E402
from app.api.main import app  # noqa: E402
from app.auth.service import UserExists, create_user  # noqa: E402
from app.db import models  # noqa: E402
from app.db.session import get_session  # noqa: E402

TENANT_ID = "t-smoke"
TENANT_SLUG = "smoke"
EMAIL = "smoke@test.com"
PASSWORD = "smoke-password-123"


def _seed_user_and_match():
    s = next(get_session())
    t = s.get(models.Tenant, TENANT_ID)
    if t is None:
        s.add(models.Tenant(
            id=TENANT_ID, slug=TENANT_SLUG, name="Smoke",
            active=True, created_at=datetime.now(UTC),
        ))
        s.flush()
    with suppress(UserExists):
        create_user(s, tenant_id=TENANT_ID, email=EMAIL,
                    password=PASSWORD, role="admin")
    # Smoke match: 611 vs 607, 2 gün sonra
    base = datetime.now(UTC)
    existing = s.execute(
        select(models.Match).where(models.Match.external_id == 99001),
    ).scalar_one_or_none()
    if not existing:
        s.add_all([
            models.Match(
                sport="football", external_id=99000,
                league_external_id=203, season=2024,
                kickoff=base - timedelta(days=10), status="FT",
                home_team_external_id=611, away_team_external_id=614,
                home_score=2, away_score=0, tenant_id=TENANT_ID,
            ),
            models.Match(
                sport="football", external_id=99001,
                league_external_id=203, season=2024,
                kickoff=base + timedelta(days=2), status="NS",
                home_team_external_id=611, away_team_external_id=607,
                home_score=None, away_score=None, tenant_id=TENANT_ID,
            ),
        ])
    s.commit()


def _login(client: TestClient) -> str:
    r = client.post("/auth/login", json={
        "email": EMAIL, "password": PASSWORD, "tenant_slug": TENANT_SLUG,
    })
    r.raise_for_status()
    return r.json()["access_token"]


def _h(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


def main() -> int:
    _seed_user_and_match()
    client = TestClient(app)
    token = _login(client)
    h = _h(token)

    cases = [
        ("/admin/tactical/match-plan", {
            "our_formation": "4-3-3", "opp_formation": "5-3-2",
            "opponent_style": "atletico_compact",
            "our_attributes": {"aerial": 0.8},
        }, lambda v: "4-3-3" in v["headline"] and v["plan_lines"]),
        ("/admin/tactical/formation-matchup", {
            "our_formation": "4-3-3", "opp_formation": "4-2-3-1",
        }, lambda v: v["advice"]),
        ("/admin/tactical/set-piece-recommend", {
            "type": "corner", "side": "long",
            "our_attributes": {"aerial": 0.85},
        }, lambda v: v["top_recommendations"]),
        ("/admin/tactical/threat-pathway", {
            "events": [
                {"start_y": 40, "end_y": 10, "threat_weight": 0.3, "is_shot": True},
                {"start_y": 35, "end_y": 15, "threat_weight": 0.4},
            ],
        }, lambda v: v["top_lane"] == "left_wing"),
        ("/admin/tactical/opportunity-window", {
            "snapshots": [
                {"minute": 60, "opp_distance_covered": 0.85, "opp_press_intensity": 0.75},
                {"minute": 75, "opp_distance_covered": 0.65, "opp_press_intensity": 0.50,
                 "opp_yellow_count": 3},
            ],
        }, lambda v: len(v["windows"]) > 0),
        ("/admin/tactical/in-match-decision", {
            "minute": 82, "our_score": 0, "opp_score": 1,
            "fatigue_avg": 0.85, "subs_left": 2,
            "yellows_in_starting_xi": 2,
        }, lambda v: any(d["priority"] == "urgent" for d in v["decisions"])),
        ("/admin/performance/consistency", {
            "samples": [{"match_id": i, "value": 7.5} for i in range(1, 6)],
        }, lambda v: v["consistency_label"] == "high"),
        ("/admin/performance/trajectory", {
            "points": [
                {"match_id": i, "value": 5.0 + i * 0.5, "game_index": i}
                for i in range(5)
            ],
        }, lambda v: v["direction"] == "improving"),
        ("/admin/performance/comparison", {
            "players": [
                {"player_id": 1, "name": "A", "kpis": {"rating": 8.0, "xt": 0.4}},
                {"player_id": 2, "name": "B", "kpis": {"rating": 6.5, "xt": 0.3}},
            ],
        }, lambda v: v["winner_name"] == "A"),
        ("/admin/performance/opponent-adjusted-rating", {
            "samples": [
                {"match_id": 1, "rating": 7.5, "opp_rating": 8.5},
                {"match_id": 2, "rating": 8.0, "opp_rating": 5.5},
                {"match_id": 3, "rating": 7.0, "opp_rating": 7.0},
            ],
        }, lambda v: v["sample_count"] == 3 and len(v["buckets"]) >= 2),
        ("/admin/performance/clutch", {
            "samples": [
                {"match_id": 1, "rating": 6.0, "flags": {}},
                {"match_id": 2, "rating": 6.2, "flags": {}},
                {"match_id": 3, "rating": 8.5, "flags": {"big_match": True}},
                {"match_id": 4, "rating": 8.6, "flags": {"big_match": True}},
                {"match_id": 5, "rating": 8.7, "flags": {"big_match": True}},
            ],
        }, lambda v: v["label"] == "clutch"),
        ("/admin/performance/anomaly", {
            "points": [
                {"match_id": 1, "rating": 7.5},
                {"match_id": 2, "rating": 7.3},
                {"match_id": 3, "rating": 7.7},
                {"match_id": 4, "rating": 7.6},
                {"match_id": 5, "rating": 7.5},
                {"match_id": 6, "rating": 5.0},  # sudden drop
            ],
        }, lambda v: any(e["type"] == "sudden_drop" for e in v["events"])),
        ("/admin/performance/team-form-health", {
            "players": [
                {"player_id": 1, "name": "Up", "ratings": [5, 6, 7, 8, 9]},
                {"player_id": 2, "name": "Down", "ratings": [9, 8, 7, 6, 5]},
            ],
        }, lambda v: v["pct_improving"] > 0 and v["pct_declining"] > 0),
    ]

    print("=== Endpoint smoke ===")
    fails = 0
    for path, payload, assertion in cases:
        r = client.post(path, json=payload, headers=h)
        ok = r.status_code == 200 and assertion(r.json()["value"])
        mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] {path} → {r.status_code}")
        if not ok:
            fails += 1
            print(f"        body: {r.text[:300]}")

    print()
    print("=== Maçı Notla round-trip ===")
    # Kaydet → seri → performans (event verisi olmadan)
    for i in range(6):
        client.post("/admin/ratings/match", json={
            "match_external_id": 50000 + i,
            "ratings": [{
                "player_external_id": 77,
                "rating": 6.5 + i * 0.25,
                "opp_rating": 7.5,
            }],
        }, headers=h)
    rp = client.get("/admin/ratings/player/77/performance", headers=h)
    rp_ok = (
        rp.status_code == 200
        and rp.json()["count"] == 6
        and rp.json()["results"]["trajectory"]["value"]["direction"] == "improving"
    )
    print(f"  [{'PASS' if rp_ok else 'FAIL'}] ratings save→performance → improving")
    if not rp_ok:
        fails += 1
        print(f"        body: {rp.text[:300]}")

    print()
    print("=== Agent integration ===")
    s = next(get_session())
    cm = ClaudeCommentator(AnthropicClient())
    tactical = TacticalAdjustmentAgent(commentator=cm)
    pre_match = PreMatchReportAgent(commentator=cm)

    t = tactical.run(s, context={
        "match_external_id": 99001, "team_external_id": 611,
    })
    pmr = pre_match.run(s, context={
        "match_external_id": 99001,
        "home_formation": "4-3-3", "away_formation": "5-3-2",
    })

    for label, output in [
        ("TacticalAdjustmentAgent v3", t.output_json),
        ("PreMatchReportAgent v2", pmr.output_json),
    ]:
        mp = output.get("match_plan")
        ok = mp is not None and "headline" in mp and "plan_lines" in mp
        mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] {label} → match_plan {'present' if ok else 'missing'}")

    print()
    if fails:
        print(f"FAILURES: {fails}")
        return 1
    print("ALL GREEN — sistem gerçekten çalışıyor")
    return 0


if __name__ == "__main__":
    sys.exit(main())
