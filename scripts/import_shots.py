"""Basit CSV'den şut içe aktar — koordinatlı event aboneliği olmadan ölçüme başla.

## Neden

Karar etkisi ölçümü koordinatlı event verisi ister (pas/taşıma/şut). Bu
StatsBomb/Opta seviyesidir ve çoğu kulüpte yoktur; tam etiketleme maç başına
2-3 saat sürer. Oysa **yalnız şutlarla** da ölçüm yapılabilir: xG farkı şuttan
hesaplanır, karar öncesi/sonrası pencere kıyaslanır.

Bir maçta ~25 şut olur; bir analistin 15 dakikalık işi. `engine.decision_impact`
pas verisi yokken hükmü "YALNIZ xG ile" diye etiketler ve güveni kırpar —
yani sistem bu veriyle çalışır ama sınırını söyler.

## CSV biçimi

Başlık satırı zorunlu; sütun sırası önemsiz. Türkçe/İngilizce başlık kabul edilir.

    dakika,takim,x,y,gol
    12.5,biz,88,52,0
    23,rakip,80,40,0
    41.2,biz,92,50,1

- `dakika`  : maç dakikası (ondalık olabilir — 45+2 için 47 yaz)
- `takim`   : `biz` / `rakip` (ya da doğrudan takım id'si)
- `x`, `y`  : saha-normalize 0-100. **Kale (100, 50)** — yani şut ne kadar
              kaleye yakınsa x o kadar büyük. Her iki takım için de böyle:
              rakibin şutu da kendi hücum yönünde kaydedilir.
- `gol`     : 1/0 (evet/hayır, true/false de olur)
- `oyuncu`  : (opsiyonel) oyuncu id'si

## Kullanım

    python -m scripts.import_shots --csv mac_sutlar.csv --tenant t-default \\
        --match-id 20260914 --our-team 217 --their-team 213 \\
        --kickoff 2026-09-14 --our-score 2 --their-score 1

Aynı dosya tekrar içe aktarılırsa satırlar güncellenir (idempotent):
kaynak `manual_shots`, event id `mac-dakika-takim` üzerinden tekilleştirilir.
"""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import UTC, datetime

from sqlalchemy import select

from app.db import models
from app.db.session import SessionLocal
from app.sports import football

SOURCE = "manual_shots"
MANUAL_LEAGUE_ID = 0

_MINUTE = ("dakika", "minute", "min", "dk")
_TEAM = ("takim", "takım", "team")
_X = ("x", "mesafe_x")
_Y = ("y", "mesafe_y")
_GOAL = ("gol", "goal", "is_goal")
_PLAYER = ("oyuncu", "player", "player_id")
_TRUE = {"1", "true", "evet", "e", "yes", "y", "gol", "var"}


def _pick(row: dict[str, str], names: tuple[str, ...]) -> str | None:
    for n in names:
        for k, v in row.items():
            if k and k.strip().lower() == n:
                return (v or "").strip()
    return None


def _parse_team(raw: str | None, our: int, their: int) -> int | None:
    if not raw:
        return None
    v = raw.strip().lower()
    if v in {"biz", "us", "our", "ev", "home"}:
        return our
    if v in {"rakip", "them", "their", "dep", "away"}:
        return their
    try:
        return int(v)
    except ValueError:
        return None


def read_rows(path: str, *, our: int, their: int) -> tuple[list[dict], list[str]]:
    """CSV → şut satırları + insan-okur hata listesi (satır numaralı)."""
    out: list[dict] = []
    errors: list[str] = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for i, row in enumerate(csv.DictReader(f), start=2):
            minute_s = _pick(row, _MINUTE)
            team = _parse_team(_pick(row, _TEAM), our, their)
            x_s, y_s = _pick(row, _X), _pick(row, _Y)
            if not minute_s or team is None or not x_s or not y_s:
                errors.append(f"satır {i}: dakika/takım/x/y eksik ya da okunamadı")
                continue
            try:
                minute, x, y = float(minute_s), float(x_s), float(y_s)
            except ValueError:
                errors.append(f"satır {i}: dakika/x/y sayı değil")
                continue
            if not (0.0 <= x <= 100.0 and 0.0 <= y <= 100.0):
                errors.append(f"satır {i}: x/y 0-100 aralığında olmalı (kale 100,50)")
                continue
            if minute < 0 or minute > 130:
                errors.append(f"satır {i}: dakika makul değil ({minute})")
                continue
            player_s = _pick(row, _PLAYER)
            out.append({
                "minute": minute, "team": team, "x": x, "y": y,
                "goal": (_pick(row, _GOAL) or "0").lower() in _TRUE,
                "player": int(player_s) if player_s and player_s.isdigit() else 0,
            })
    return out, errors


def import_shots(
    rows: list[dict], *, tenant: str, match_id: int, our: int, their: int,
    kickoff: datetime, our_score: int | None, their_score: int | None,
    session=None,
) -> dict:
    """Şutları DB'ye yaz (idempotent).

    `session` verilirse o kullanılır ve KAPATILMAZ — testler ve çağıran kod
    kendi oturumunu yönetebilsin diye. Verilmezse kendi oturumunu açar.
    """
    import contextlib

    own = session is None
    ctx = SessionLocal() if own else contextlib.nullcontext(session)
    with ctx as s:
        s.info["tenant_id"] = tenant
        if s.get(models.Tenant, tenant) is None:
            s.add(models.Tenant(id=tenant, slug=tenant, name=tenant,
                                settings_json="{}", active=True,
                                created_at=datetime.now(UTC)))
        match = s.execute(select(models.Match).where(
            models.Match.sport == football.SPORT_NAME,
            models.Match.external_id == match_id,
            models.Match.tenant_id == tenant,
        )).scalar_one_or_none()
        created = match is None
        if created:
            s.add(models.Match(
                sport=football.SPORT_NAME, external_id=match_id,
                league_external_id=MANUAL_LEAGUE_ID, season=kickoff.year,
                kickoff=kickoff, status="FT",
                home_team_external_id=our, away_team_external_id=their,
                home_score=our_score, away_score=their_score, tenant_id=tenant,
            ))
            s.flush()

        existing = {
            e.source_event_id: e for e in s.execute(select(models.EventRow).where(
                models.EventRow.sport == football.SPORT_NAME,
                models.EventRow.match_external_id == match_id,
                models.EventRow.source == SOURCE,
            )).scalars()
        }
        written = updated = 0
        now = datetime.now(UTC)
        for r in rows:
            eid = f"{match_id}-{r['minute']:.2f}-{r['team']}"
            row = existing.get(eid)
            values = dict(
                team_external_id=r["team"], player_external_id=r["player"],
                minute=r["minute"], period=1 if r["minute"] < 45 else 2,
                start_x=r["x"], start_y=r["y"],
                is_goal=r["goal"], outcome="goal" if r["goal"] else "off_t",
            )
            if row is not None:
                for k, v in values.items():
                    setattr(row, k, v)
                updated += 1
                continue
            s.add(models.EventRow(
                sport=football.SPORT_NAME, tenant_id=tenant, source=SOURCE,
                source_event_id=eid, match_external_id=match_id,
                event_type="shot", end_x=None, end_y=None, body_part=None,
                pattern="regular", possession_id=None, key_pass=False,
                raw_json=None, created_at=now, **values,
            ))
            written += 1
        s.commit()
    return {"match_id": match_id, "match_created": created,
            "shots_written": written, "shots_updated": updated}


def main() -> int:
    p = argparse.ArgumentParser(description="CSV'den şut içe aktar (ölçüme hızlı başlangıç)")
    p.add_argument("--csv", required=True)
    p.add_argument("--tenant", required=True)
    p.add_argument("--match-id", type=int, required=True)
    p.add_argument("--our-team", type=int, required=True)
    p.add_argument("--their-team", type=int, required=True)
    p.add_argument("--kickoff", default=None, help="YYYY-MM-DD (varsayılan: bugün)")
    p.add_argument("--our-score", type=int, default=None)
    p.add_argument("--their-score", type=int, default=None)
    p.add_argument("--dry-run", action="store_true", help="Yazma; yalnız doğrula")
    args = p.parse_args()

    rows, errors = read_rows(args.csv, our=args.our_team, their=args.their_team)
    print(f"okunan şut: {len(rows)} · hatalı satır: {len(errors)}")
    for e in errors[:10]:
        print(f"  ! {e}")
    if len(errors) > 10:
        print(f"  … {len(errors) - 10} hata daha")
    if not rows:
        print("içe aktarılacak şut yok — CSV başlıklarını kontrol et "
              "(dakika,takim,x,y,gol)")
        return 1
    ours = sum(1 for r in rows if r["team"] == args.our_team)
    goals = sum(1 for r in rows if r["goal"])
    print(f"  bizim {ours} · rakip {len(rows) - ours} · gol {goals}")
    if args.dry_run:
        print("(dry-run — yazılmadı)")
        return 0

    kickoff = (datetime.fromisoformat(args.kickoff).replace(tzinfo=UTC)
               if args.kickoff else datetime.now(UTC))
    report = import_shots(
        rows, tenant=args.tenant, match_id=args.match_id, our=args.our_team,
        their=args.their_team, kickoff=kickoff,
        our_score=args.our_score, their_score=args.their_score,
    )
    print("\n=== Şut Ingest ===")
    for k, v in report.items():
        print(f"  {k}: {v}")
    print("\nSıradaki adım: kararları kaydet, sonra ölç →")
    print(f"  POST /admin/matches/{args.match_id}/decisions/auto-outcome")
    return 0


if __name__ == "__main__":
    sys.exit(main())
