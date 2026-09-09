"""Karar külliyatı: motorun kendi önerilerini karar olarak kaydet → ölç → ATFET.

## Neden bu script var

Sistem kendi isabetini ölçebiliyordu ama **neden güvendiğini kaydetmiyordu**:
74 kararın hepsinde `decisions.context_json` boştu. Kalibrasyon o yüzden yalnız
"sistem fazla güvenli (%84 diyor, %58 tutuyor)" diyebiliyor, HANGİ sürücünün
yanılttığını söyleyemiyordu. Atıf olmadan ağırlık değiştirmek tahmindir.

Bu script döngüyü kapatır ve **tekrarlanabilir** kılar:

1. `seed`  — her maçta belirli dakikalarda context motorunu çalıştır, çıkan
             öneriyi kararla birlikte **güven sürücüleriyle** kaydet
2. `score` — `auto-outcome` mantığıyla her kararın gerçek etkisini ölç
3. `report`— ölçülmüş kararlardan sürücü karnesi çıkar (hangi sürücü ayırıyor?)

## Kararlar UYDURULMAZ

Öneriyi de güveni de sistemin kendisi üretir; script yalnız kaydeder. Sonuç
gerçek event verisinden (xG/xT farkı) ölçülür. Yani karne sistemin kendi
güvenini tartar.

## Kullanım

    venv\\Scripts\\python.exe -m scripts.decision_corpus seed --tenant t-default --team 217
    venv\\Scripts\\python.exe -m scripts.decision_corpus score --tenant t-default
    venv\\Scripts\\python.exe -m scripts.decision_corpus report --tenant t-default --team 217

`seed` aynı maç+dakika için ikinci kez çalıştırılırsa o karar ATLANIR
(idempotent) — külliyat şişmesin.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime

from sqlalchemy import select

from app.db import models
from app.db.session import SessionLocal
from app.sports import football

# Maç akışında anlamlı, birbirinden uzak anlar: erken ayar, devre öncesi,
# devre sonrası, klasik değişiklik penceresi, kapanış.
DEFAULT_TICKS = (28.0, 40.0, 55.0, 66.0, 78.0)
SOURCE_NOTE = "[külliyat] motor önerisi"


# StatsBomb açık verisinde Barcelona'nın bulunduğu La Liga sezonları.
# (competition_id, season_id) — 4=2018/19, 42=2019/20, 90=2020/21
LALIGA_SEASONS = ((11, 4), (11, 42), (11, 90))


def import_matches(args: argparse.Namespace) -> int:
    """StatsBomb'dan takımın maçlarını `matches` tablosuna aktar.

    `ingest_statsbomb_events` yalnız DB'de ZATEN olan maçları işliyor; külliyatı
    büyütmek için önce maç kayıtları gerekiyor. Idempotent: var olan atlanır.
    """
    from app.data.sources.statsbomb_open import StatsBombOpen

    src = StatsBombOpen()
    with SessionLocal() as s:
        s.info["tenant_id"] = args.tenant
        if s.get(models.Tenant, args.tenant) is None:
            s.add(models.Tenant(id=args.tenant, slug=args.tenant, name=args.tenant,
                                settings_json="{}", active=True,
                                created_at=datetime.now(UTC)))
        var = {m.external_id for m in s.execute(select(models.Match).where(
            models.Match.sport == football.SPORT_NAME,
        )).scalars()}

        eklenen = atlanan = 0
        for comp_id, season_id in LALIGA_SEASONS:
            try:
                rows = src.get_matches(competition_id=comp_id, season_id=season_id)
            except Exception as e:          # noqa: BLE001 — bir sezon düşerse ötekiler sürsün
                print(f"  sezon {comp_id}/{season_id} alınamadı ({type(e).__name__})")
                continue
            for m in rows:
                home, away = m["home_team"], m["away_team"]
                ids = (home["home_team_id"], away["away_team_id"])
                if args.team not in ids:
                    continue
                mid = int(m["match_id"])
                if mid in var:
                    atlanan += 1
                    continue
                try:
                    kickoff = datetime.fromisoformat(
                        f"{m['match_date']}T{m.get('kick_off') or '20:00:00'}+00:00")
                except ValueError:
                    kickoff = datetime.now(UTC)
                s.add(models.Match(
                    sport=football.SPORT_NAME, external_id=mid,
                    league_external_id=comp_id, season=int(season_id),
                    kickoff=kickoff, status="FT",
                    home_team_external_id=ids[0], away_team_external_id=ids[1],
                    home_score=int(m.get("home_score") or 0),
                    away_score=int(m.get("away_score") or 0),
                    tenant_id=args.tenant,
                ))
                var.add(mid)
                eklenen += 1
        s.commit()
    print(f"maç eklendi: {eklenen} · zaten vardı: {atlanan}")
    if eklenen:
        print("Sıradaki adım: python -m scripts.ingest_statsbomb_events "
              f"--tenant {args.tenant} --team {args.team} --limit {eklenen}")
    return 0


def _matches(session, *, tenant: str, team: int, limit: int) -> list[models.Match]:
    rows = session.execute(
        select(models.Match).where(
            models.Match.sport == football.SPORT_NAME,
            models.Match.tenant_id == tenant,
        ).order_by(models.Match.kickoff)
    ).scalars().all()
    ours = [m for m in rows
            if team in (m.home_team_external_id, m.away_team_external_id)]
    return ours[:limit] if limit else ours


def _has_events(session, match_id: int, tenant: str) -> int:
    return session.execute(
        select(models.EventRow).where(
            models.EventRow.sport == football.SPORT_NAME,
            models.EventRow.match_external_id == match_id,
            models.EventRow.tenant_id == tenant,
        ).limit(1)
    ).scalars().first() is not None


def seed(args: argparse.Namespace) -> int:
    """Context motorunu çalıştır, önerileri SÜRÜCÜLERİYLE karar olarak yaz."""
    # Panelin TAMAMI çalıştırılır (tek tek motorlar değil): kararı üreten yol
    # ile ölçülen yol aynı olmalı, yoksa karne başka bir sistemi tartar.
    from app.api.admin import live_decision_endpoint

    with SessionLocal() as s:
        s.info["tenant_id"] = args.tenant
        matches = _matches(s, tenant=args.tenant, team=args.team, limit=args.limit)
        if not matches:
            print(f"maç bulunamadı (tenant={args.tenant}, takım={args.team})")
            return 1

        var: dict[tuple[int, float], bool] = {
            (d.match_external_id, d.minute): True
            for d in s.execute(select(models.Decision).where(
                models.Decision.sport == football.SPORT_NAME,
                models.Decision.tenant_id == args.tenant,
            )).scalars()
        }

        yazilan = atlanan = sinyalsiz = 0
        for m in matches:
            if not _has_events(s, m.external_id, args.tenant):
                continue
            for tick in DEFAULT_TICKS:
                if (m.external_id, tick) in var:
                    atlanan += 1
                    continue
                try:
                    payload = live_decision_endpoint(
                        match_id=m.external_id, my_team_id=args.team,
                        current_minute=tick, star_player_id=None,
                        draw_is_enough=False, must_win=False, session=s,
                    )
                except Exception as e:      # noqa: BLE001 — külliyat üretimi sürmeli
                    print(f"  maç {m.external_id} dk {tick:.0f}: hazırlanamadı "
                          f"({type(e).__name__}) — atlandı")
                    continue
                ctx = payload.get("context") or {}
                primary = ctx.get("primary")
                if not primary:
                    sinyalsiz += 1
                    continue

                s.add(models.Decision(
                    sport=football.SPORT_NAME, tenant_id=args.tenant,
                    match_external_id=m.external_id, team_external_id=args.team,
                    minute=tick, period=1 if tick < 45 else 2,
                    decision_type=_karar_tipi(primary.get("theme")),
                    notes=(SOURCE_NOTE + " · " + str(primary.get("rationale") or ""))[:512],
                    created_at=datetime.now(UTC),
                    recommended=True,
                    confidence=primary.get("confidence"),
                    # ASIL YENİLİK: güvenin sayısal kırılımı kararla saklanır.
                    context_json=json.dumps({
                        "confidence_terms": primary.get("confidence_terms") or {},
                        "signal_type": primary.get("signal_type"),
                        "theme": primary.get("theme"),
                        "urgency": primary.get("urgency"),
                        "priority": primary.get("priority"),
                        "score_state": _skor_durumu(m, args.team),
                        "supporting_keys": list(primary.get("supporting_keys") or ()),
                    }, ensure_ascii=False),
                    outcome="pending",
                ))
                yazilan += 1
        s.commit()

    print(f"karar yazıldı: {yazilan} · zaten vardı: {atlanan} · sinyal yok: {sinyalsiz}")
    if yazilan == 0 and atlanan:
        print("(hepsi mevcut — külliyat büyütmek için --limit artır)")
    return 0


def _karar_tipi(theme: str | None) -> str:
    return "substitution" if theme == "change_personnel" else "tactical"


def _skor_durumu(match, team: int) -> str:
    h, a = match.home_score, match.away_score
    if h is None or a is None:
        return "unknown"
    mine, theirs = (h, a) if match.home_team_external_id == team else (a, h)
    return "leading" if mine > theirs else "trailing" if mine < theirs else "drawing"


def score(args: argparse.Namespace) -> int:
    """Her maç için kararların gerçek etkisini ölç (auto-outcome mantığı)."""
    from app.api.admin import _decision_impacts

    with SessionLocal() as s:
        s.info["tenant_id"] = args.tenant
        match_ids = sorted({
            d.match_external_id for d in s.execute(select(models.Decision).where(
                models.Decision.sport == football.SPORT_NAME,
                models.Decision.tenant_id == args.tenant,
            )).scalars()
        })
        yazilan = yetersiz = 0
        for mid in match_ids:
            try:
                impacts, meta = _decision_impacts(s, mid, window_min=15.0)
            except Exception as e:          # noqa: BLE001
                print(f"  maç {mid}: ölçülemedi ({type(e).__name__})")
                continue
            if meta.get("note"):
                continue
            by_id = {r.id: r for r in s.execute(select(models.Decision).where(
                models.Decision.sport == football.SPORT_NAME,
                models.Decision.match_external_id == mid,
                models.Decision.tenant_id == args.tenant,
            )).scalars()}
            for res in impacts:
                imp = res.value
                row = by_id.get(imp.decision_id)
                if row is None:
                    continue
                if imp.verdict == "insufficient_data":
                    yetersiz += 1
                    continue
                row.outcome = imp.verdict
                # admin.decisions_auto_outcome ile AYNI alanlar yazılmalı;
                # farklı yazarsak külliyat ile ürünün ölçtüğü şey ayrışır.
                row.outcome_value = imp.xg_diff_delta
                row.outcome_notes = f"[oto] {imp.verdict_reason}"[:512]
                row.outcome_recorded_at = datetime.now(UTC)
                yazilan += 1
        s.commit()
    print(f"sonuç yazıldı: {yazilan} · ölçülemedi: {yetersiz}")
    return 0


def report(args: argparse.Namespace) -> int:
    """Ölçülmüş kararlardan sürücü karnesi: hangi sürücü sonucu ayırıyor?"""
    from app.engine.confidence.attribution import attribute

    with SessionLocal() as s:
        s.info["tenant_id"] = args.tenant
        rows = [
            d for d in s.execute(select(models.Decision).where(
                models.Decision.sport == football.SPORT_NAME,
                models.Decision.tenant_id == args.tenant,
                models.Decision.team_external_id == args.team,
            )).scalars()
            if d.outcome in {"positive", "negative", "neutral"} and d.context_json
        ]

    samples: list[tuple[dict[str, float], bool]] = []
    for d in rows:
        if not d.context_json:
            continue
        try:
            ctx = json.loads(d.context_json)
        except (ValueError, TypeError):
            continue
        terms = {k: float(v) for k, v in (ctx.get("confidence_terms") or {}).items()
                 if isinstance(v, (int, float))}
        if not terms:
            continue
        # "neutral" başarı sayılmaz: karar ölçülebildi ama fark üretmedi.
        samples.append((terms, d.outcome == "positive"))

    print(f"\n=== Sürücü Karnesi (n={len(samples)}) ===")
    if not samples:
        print("  Sürücülü ölçülmüş karar yok.")
        print("  Önce:  seed  →  score  (eski kararlarda context_json boştur)")
        return 1

    rep = attribute(samples)
    print(f"  {rep.headline}\n")
    print(f"  {'sürücü':<18}{'AUC':>6}{'fark':>9}{'olumlu':>9}{'olumsuz':>9}  hüküm")
    print("  " + "-" * 74)
    for d in rep.drivers:
        print(f"  {d.driver:<18}{d.auc:>6.2f}{d.lift:>+9.3f}"
              f"{d.mean_positive:>9.3f}{d.mean_negative:>9.3f}  {d.verdict}")
    print()
    for d in rep.drivers:
        if d.verdict in {"TERS", "ayırıyor"}:
            print(f"  · {d.driver}: {d.note}")
    print()
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Karar külliyatı: üret → ölç → atfet")
    sub = p.add_subparsers(dest="cmd", required=True)

    for ad, fn, yardim in (
        ("import", import_matches, "StatsBomb'dan takımın maçlarını DB'ye aktar"),
        ("seed", seed, "Motor önerilerini sürücüleriyle karar olarak kaydet"),
        ("score", score, "Kararların gerçek etkisini ölç"),
        ("report", report, "Sürücü karnesi: hangi sürücü sonucu ayırıyor?"),
    ):
        c = sub.add_parser(ad, help=yardim)
        c.add_argument("--tenant", default="t-default")
        c.add_argument("--team", type=int, default=217)
        c.add_argument("--limit", type=int, default=0, help="0 = tüm maçlar")
        c.set_defaults(func=fn)

    args = p.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
