"""Video takibi JSON'unu (scripts/track_video.py çıktısı) tracking_frames'e al.

- matches satırı yoksa sentetik bir maç açar (lig 0, skor yok) — overlay
  sayfaları /tracking/matches listesinden seçer.
- Mevcut kareleri siler, yeniden yazar (replace).

Kullanım:
    python -m scripts.ingest_tracking_json --json frames.json --tenant t-default
    python -m scripts.ingest_tracking_json --json frames.json --tenant t-default --match-id 990002 --label "Antrenman 08.09"
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime

from sqlalchemy import select

from app.data.ingest.tracking import delete_match_frames, ingest_tracking_match
from app.data.sources.video_tracking import VideoJsonTrackingSource
from app.db import models
from app.db.session import SessionLocal
from app.sports import football

VIDEO_LEAGUE_ID = 0


def ensure_match(session, *, match_id: int, tenant_id: str, home: int, away: int) -> bool:
    exists = session.execute(
        select(models.Match).where(
            models.Match.sport == football.SPORT_NAME,
            models.Match.external_id == match_id,
            models.Match.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()
    if exists is not None:
        return False
    if session.get(models.Tenant, tenant_id) is None:
        session.add(models.Tenant(
            id=tenant_id, slug=tenant_id, name=tenant_id, settings_json="{}",
            active=True, created_at=datetime.now(UTC),
        ))
    session.add(models.Match(
        sport=football.SPORT_NAME, external_id=match_id,
        league_external_id=VIDEO_LEAGUE_ID, season=datetime.now(UTC).year,
        kickoff=datetime.now(UTC), status="FT",
        home_team_external_id=home, away_team_external_id=away,
        home_score=None, away_score=None, tenant_id=tenant_id,
    ))
    session.flush()
    return True


def ingest_json(
    *, path: str, tenant_id: str, match_id: int | None = None, append: bool = False,
) -> dict:
    """JSON kareleri → tracking_frames.

    `append=True`: mevcut kareler silinmez — canlı maçta ardışık segmentler
    aynı maça eklenir (bkz. scripts/track_live.py). Aynı zaman damgalı kare
    yeniden gelirse güncellenir (ingest zaten idempotent).
    """
    from app.db.base import Base
    from app.db.session import engine
    from scripts.dev_seed import _sync_missing_columns

    Base.metadata.create_all(engine)
    _sync_missing_columns(engine)

    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    mid = int(match_id or payload["match_external_id"])
    home = int(payload.get("home_team_external_id") or 0)
    away = int(payload.get("away_team_external_id") or 0)

    with SessionLocal() as session:
        session.info["tenant_id"] = tenant_id
        created = ensure_match(session, match_id=mid, tenant_id=tenant_id, home=home, away=away)
        removed = 0 if append else delete_match_frames(
            session, sport=football.SPORT_NAME, match_external_id=mid,
        )
        report = ingest_tracking_match(
            session, VideoJsonTrackingSource(path), match_external_id=mid, sport=football.SPORT_NAME,
        )
        session.commit()
    return {
        "match_id": mid, "tenant_id": tenant_id, "match_created": created,
        "frames_removed": removed, "frames_written": report.frames_written,
        "source_video": payload.get("video"),
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Video tracking JSON → tracking_frames")
    p.add_argument("--json", required=True)
    p.add_argument("--tenant", required=True)
    p.add_argument("--match-id", type=int, default=None, help="JSON'daki id yerine bu id altında yaz")
    p.add_argument("--append", action="store_true",
                   help="Mevcut kareleri silme — canlı maçta segment ekleme")
    args = p.parse_args()
    report = ingest_json(path=args.json, tenant_id=args.tenant, match_id=args.match_id,
                         append=args.append)
    print("\n=== Video Tracking Ingest ===")
    for k, v in report.items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
