"""Bir kulübün StatsBomb açık-veri maçlarını YEREL dosyalardan DB'ye yaz.

## Neden var

`measure_sub_ranking` motorun bileşik skorunu (yorgunluk, pas isabeti) hesaplamak
için maç olaylarını DB'den okur. Barcelona külliyatı için bu veri zaten
içerideydi; ikinci bir kulüpte aynı ölçümü tekrar etmek için o kulübün
maçlarının da girmesi gerekir. `ingest_statsbomb_events` tek tek maçları
GitHub'dan çeker ve `matches` tablosunda satır bekler; burada ikisi birden,
yerel dosyadan yapılır — 300 MB'lık olay setini ikinci kez indirmemek için.

Ölçüm tekrar üretilebilir olsun diye script depoda; scratch'te değil.

## Kullanım

    venv\\Scripts\\python.exe -m scripts.ingest_club_matches
        --tenant psg --team 131
        --matches C:\\sb-matches\\7_27.json --matches C:\\sb-matches\\7_108.json
        --events-dir C:\\sb-psg

`--matches`: StatsBomb `matches/{comp}/{season}.json` (birden çok verilebilir).
`--events-dir`: düz klasörde `{match_id}.json`. Yalnız `--team`'in oynadığı
maçlar alınır. Idempotent: var olan maç/olay satırları atlanır.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.data.ingest.event import ingest_events_for_match
from app.data.sources.statsbomb_open import StatsBombOpen
from app.db import models
from app.db.session import SessionLocal
from app.sports import football


class LocalStatsBomb(StatsBombOpen):
    """`get_events` yerel klasörden okur; başka hiçbir şey değişmez."""

    def __init__(self, events_dir: Path) -> None:
        super().__init__()
        self._dir = events_dir

    def get_events(self, match_id: int) -> list[dict[str, Any]]:
        data = json.loads((self._dir / f"{match_id}.json").read_text(encoding="utf-8"))
        return list(data)


def _kickoff(m: dict[str, Any]) -> datetime:
    date = m.get("match_date") or "1970-01-01"
    time = (m.get("kick_off") or "00:00:00.000")[:8]
    return datetime.fromisoformat(f"{date}T{time}").replace(tzinfo=UTC)


def _team_matches(files: list[Path], team: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for f in files:
        for m in json.loads(f.read_text(encoding="utf-8")):
            if team in (m["home_team"]["home_team_id"], m["away_team"]["away_team_id"]):
                out.append(m)
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="Kulübün maçlarını yerel dosyalardan DB'ye yaz")
    p.add_argument("--tenant", required=True)
    p.add_argument("--team", type=int, required=True)
    p.add_argument("--matches", type=Path, action="append", required=True,
                   help="StatsBomb matches/{comp}/{season}.json; tekrarlanabilir")
    p.add_argument("--events-dir", type=Path, required=True)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    matches = _team_matches(args.matches, args.team)
    have = [m for m in matches if (args.events_dir / f"{m['match_id']}.json").is_file()]
    print(f"{len(matches)} maç listede, {len(have)} tanesinin olay dosyası var")
    if args.dry_run:
        return 0

    src = LocalStatsBomb(args.events_dir)
    added = skipped = 0
    events = 0
    with SessionLocal() as s:
        s.info["tenant_id"] = args.tenant
        for m in have:
            mid = int(m["match_id"])
            exists = s.execute(select(models.Match.id).where(
                models.Match.sport == football.SPORT_NAME,
                models.Match.external_id == mid,
                models.Match.tenant_id == args.tenant,
            )).scalar_one_or_none()
            if exists is None:
                s.add(models.Match(
                    sport=football.SPORT_NAME, external_id=mid,
                    league_external_id=int(m["competition"]["competition_id"]),
                    season=int(m["season"]["season_id"]),
                    kickoff=_kickoff(m), status="FT",
                    home_team_external_id=int(m["home_team"]["home_team_id"]),
                    away_team_external_id=int(m["away_team"]["away_team_id"]),
                    home_score=int(m.get("home_score") or 0),
                    away_score=int(m.get("away_score") or 0),
                    tenant_id=args.tenant,
                ))
                s.flush()
                added += 1
            else:
                skipped += 1
            rep = ingest_events_for_match(s, src, match_external_id=mid, tenant_id=args.tenant)
            events += rep.rows_inserted
            s.commit()
    print(f"maç: {added} eklendi, {skipped} zaten vardı · {events} olay yazıldı → tenant {args.tenant}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
