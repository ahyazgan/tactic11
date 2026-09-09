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

from sqlalchemy import delete, select

from app.data.ingest.tracking import delete_match_frames, ingest_tracking_match
from app.data.sources.video_tracking import VideoJsonTrackingSource
from app.db import models
from app.db.session import SessionLocal
from app.sports import football

VIDEO_LEAGUE_ID = 0
# Takipten ÇIKARILMIŞ pasların kaynak etiketi. Sağlayıcı event'lerinden
# (statsbomb_open, manual_shots) AYRI tutulur ki:
#   - istenmezse tek sorguyla dışlanabilsin,
#   - motorlar bunların TAHMİN olduğunu bilebilsin,
#   - yeniden ingest idempotent olsun (source + source_event_id tekil).
DERIVED_PASS_SOURCE = "video_passes"


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


def ingest_derived_passes(
    session, payload: dict, *, tenant_id: str, match_id: int, replace: bool,
) -> int:
    """JSON'daki `derived_passes` → events tablosu (pas olayları).

    Neden gerekli: `app/tracking/passes.py` pasları çıkarıyordu ama hiçbir yere
    YAZILMIYORDU — hesaplanıp JSON'da kalıyordu, dolayısıyla xT / ileri pas /
    karar etkisi motorları kulüp videosundan beslenemiyordu. Bu fonksiyon o
    zinciri kapatır.

    Dürüstlük: hepsi TAHMİNDİR. Gerçek yayın verisiyle ölçüldü (SkillCorner,
    `scripts/validate_passes.py`) — geçerli kesinlik %72, gözlemlenebilir
    geçişlerin %80'i yakalanıyor. `outcome` alanı tamamlanma durumunu taşır;
    `raw_json` ham ölçümleri (uçuş süresi, mesafe, topun enterpole olup olmadığı)
    saklar ki sonradan güvenilirlik süzülebilsin.
    """
    passes = payload.get("derived_passes") or []
    if not passes:
        return 0

    if replace:
        session.execute(
            delete(models.EventRow).where(
                models.EventRow.sport == football.SPORT_NAME,
                models.EventRow.tenant_id == tenant_id,
                models.EventRow.match_external_id == match_id,
                models.EventRow.source == DERIVED_PASS_SOURCE,
            )
        )

    mevcut = {
        e.source_event_id for e in session.execute(
            select(models.EventRow).where(
                models.EventRow.sport == football.SPORT_NAME,
                models.EventRow.tenant_id == tenant_id,
                models.EventRow.match_external_id == match_id,
                models.EventRow.source == DERIVED_PASS_SOURCE,
            )
        ).scalars()
    }

    now = datetime.now(UTC)
    yazilan = 0
    for p in passes:
        # Tekil kimlik: dakika + veren + alan. Aynı segment yeniden işlenirse
        # çift kayıt oluşmaz.
        eid = (f"{p['minute']:.4f}-{p['from_player_external_id']}"
               f"-{p['to_player_external_id']}")
        if eid in mevcut:
            continue
        session.add(models.EventRow(
            sport=football.SPORT_NAME, tenant_id=tenant_id,
            source=DERIVED_PASS_SOURCE, source_event_id=eid,
            match_external_id=match_id,
            team_external_id=p.get("team_external_id"),
            player_external_id=p.get("from_player_external_id"),
            event_type="pass",
            minute=float(p["minute"]),
            period=1 if float(p["minute"]) < 45 else 2,
            start_x=p.get("start_x"), start_y=p.get("start_y"),
            end_x=p.get("end_x"), end_y=p.get("end_y"),
            # "completed" (d ile) — SAĞLAYICI ingest'iyle AYNI sözcük olmalı.
            # `app/data/ingest/event.py` bunu yazıyor ve loader `completed`
            # alanını buradan türetiyor. "complete" yazmak her pası
            # tamamlanmamış sayar ve xT SESSİZCE sıfır çıkar.
            outcome="completed" if p.get("complete", True) else "incomplete",
            body_part=None, pattern="regular", possession_id=None,
            is_goal=False, key_pass=False,
            raw_json=json.dumps({
                "derived": True,
                "distance_m": p.get("distance_m"),
                "flight_seconds": p.get("flight_seconds"),
                "ball_estimated": p.get("ball_estimated"),
                "to_player_external_id": p.get("to_player_external_id"),
            }, ensure_ascii=False),
            created_at=now,
        ))
        mevcut.add(eid)
        yazilan += 1
    return yazilan


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
        # Takipten çıkarılan paslar → events. `append` canlı segment akışı
        # demektir; orada var olanı SİLMEK önceki segmentlerin paslarını
        # yok ederdi, o yüzden replace yalnız tam-video ingest'inde.
        passes_written = ingest_derived_passes(
            session, payload, tenant_id=tenant_id, match_id=mid, replace=not append,
        )
        session.commit()
    return {
        "match_id": mid, "tenant_id": tenant_id, "match_created": created,
        "frames_removed": removed, "frames_written": report.frames_written,
        "passes_written": passes_written,
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
