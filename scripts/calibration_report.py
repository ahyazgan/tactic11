"""Kalibrasyon kanıtı — pilot kulübe gösterilecek somut sayı.

Her "AI futbol analizi" doğru tahmin iddia eder. Bizi ayıran: tahminlerimizin
kalibre olduğunu **sayıyla** gösterebilmek. Bu script, Süper Lig fixture
verisindeki tamamlanmış (FT) maçlar üzerinde sızıntısız bir backtest koşar:

  Her FT maçı için → SADECE o maçtan ÖNCEKİ maçlardan form hesapla →
  engine.predict (Dixon-Coles) ile 1X2 olasılığı üret → gerçek sonuçla eşle →
  engine.calibration ile Brier + log loss + ECE raporla.

Sızıntı yok: bir maçın tahmini, o maçın sonucunu görmeden üretilir.

Kullanım:
    python scripts/calibration_report.py                 # tty rapor
    python scripts/calibration_report.py --output md     # slide için markdown
    python scripts/calibration_report.py --min-prior 3   # min geçmiş maç eşiği

Çevre: pilot_demo ile aynı — SQLite + USE_FIXTURES, kota harcamaz.
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid as _uuid
from datetime import UTC, datetime
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite:///./_calibration_demo.db")
os.environ.setdefault("USE_FIXTURES", "true")
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ.setdefault("JWT_SECRET_KEY", "calibration-demo-secret-key-32-byte")


def _reset_db() -> None:
    db = os.environ["DATABASE_URL"]
    if db.startswith("sqlite:///"):
        path = Path(db.replace("sqlite:///", ""))
        if path.exists():
            path.unlink()


def _migrate() -> None:
    import alembic.command as command
    from alembic.config import Config
    cfg = Config(str(_PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_PROJECT_ROOT / "alembic"))
    command.upgrade(cfg, "head")


def _seed_and_sync() -> str:
    """Tenant oluştur + Süper Lig fixture sync. tenant_id döner."""
    from app.data.ingest import sync_league
    from app.data.sources.api_football import APIFootball
    from app.db import models
    from app.db.session import SessionLocal
    tenant_id = str(_uuid.uuid4())
    with SessionLocal() as s:
        s.add(models.Tenant(
            id=tenant_id, slug="calibration-demo",
            name="Calibration Demo", settings_json="{}",
            active=True, created_at=datetime.now(UTC),
        ))
        s.commit()
    with SessionLocal() as s:
        s.info["tenant_id"] = tenant_id
        sync_league(s, APIFootball(), league_id=203, season=2024)
    return tenant_id


def _outcome(home_score: int, away_score: int) -> str:
    if home_score > away_score:
        return "home"
    if home_score < away_score:
        return "away"
    return "draw"


def _build_samples(tenant_id: str, *, min_prior: int) -> list[tuple]:
    """Sızıntısız backtest: her FT maçı için sadece geçmiş maçlardan tahmin.

    Döner: (prob_home, prob_draw, prob_away, actual_outcome) listesi.
    """
    from sqlalchemy import or_, select

    from app.db import models
    from app.db.session import SessionLocal
    from app.engine.form import compute_form
    from app.engine.predict import compute_predict
    from app.sports import football

    samples: list[tuple] = []
    with SessionLocal() as s:
        s.info["tenant_id"] = tenant_id
        finished = list(s.execute(
            select(models.Match).where(
                models.Match.sport == football.SPORT_NAME,
                models.Match.status.in_(tuple(football.FINISHED_STATUSES)),
                models.Match.home_score.isnot(None),
                models.Match.away_score.isnot(None),
            ).order_by(models.Match.kickoff)
        ).scalars())

        for m in finished:
            # SADECE bu maçtan önceki maçlar (sızıntı yok)
            def _prior(team_id: int, before: datetime) -> list:
                return list(s.execute(
                    select(models.Match).where(
                        models.Match.sport == football.SPORT_NAME,
                        models.Match.kickoff < before,
                        models.Match.status.in_(tuple(football.FINISHED_STATUSES)),
                        or_(
                            models.Match.home_team_external_id == team_id,
                            models.Match.away_team_external_id == team_id,
                        ),
                    )
                ).scalars())

            home_prior = _prior(m.home_team_external_id, m.kickoff)
            away_prior = _prior(m.away_team_external_id, m.kickoff)
            if len(home_prior) < min_prior or len(away_prior) < min_prior:
                continue  # yeterli geçmiş yok → atla (güvenilir tahmin değil)

            home_form = compute_form(m.home_team_external_id, home_prior, last_n=5).value
            away_form = compute_form(m.away_team_external_id, away_prior, last_n=5).value
            p = compute_predict(
                home_form, away_form,
                home_team_id=m.home_team_external_id,
                away_team_id=m.away_team_external_id,
            ).value
            samples.append((
                p.prob_home_win, p.prob_draw, p.prob_away_win,
                _outcome(m.home_score, m.away_score),
            ))
    return samples


def _baseline_brier(samples: list[tuple]) -> float | None:
    """Naif baz çizgi: sabit lig-ortalaması olasılığı (home %45 / draw %27 /
    away %28) — modelin bunu geçip geçmediğini görmek için referans."""
    if not samples:
        return None
    ph, pd, pa = 0.45, 0.27, 0.28
    total = 0.0
    for _, _, _, actual in samples:
        oh = 1.0 if actual == "home" else 0.0
        od = 1.0 if actual == "draw" else 0.0
        oa = 1.0 if actual == "away" else 0.0
        total += (ph - oh) ** 2 + (pd - od) ** 2 + (pa - oa) ** 2
    return total / len(samples)


def run(*, min_prior: int) -> dict:
    from app.engine.calibration import compute_calibration
    _reset_db()
    _migrate()
    tenant_id = _seed_and_sync()
    samples = _build_samples(tenant_id, min_prior=min_prior)
    report = compute_calibration(
        samples, engine="engine.predict", engine_version="backtest",
    ).value
    return {
        "sample_count": report.sample_count,
        "brier_score": report.brier_score,
        "log_loss": report.log_loss,
        "ece": report.expected_calibration_error,
        "buckets": report.home_outcome_buckets,
        "baseline_brier": _baseline_brier(samples),
        "min_prior": min_prior,
    }


def _grade(brier: float | None) -> str:
    if brier is None:
        return "—"
    if brier < 0.55:
        return "✓ hedef altı (<0.55)"
    if brier < 0.62:
        return "~ kabul edilebilir"
    return "⚠ iyileştirme gerek"


def _render_tty(r: dict) -> None:
    print()
    print("\033[1;36m" + "═" * 64 + "\033[0m")
    print("\033[1;36m 📊 KALİBRASYON RAPORU — engine.predict (Dixon-Coles)\033[0m")
    print("\033[1;36m" + "═" * 64 + "\033[0m\n")
    print(f"  Backtest örneği (sızıntısız) ...... {r['sample_count']} maç")
    print(f"  Min geçmiş maç eşiği .............. {r['min_prior']}")
    print()
    b = r["brier_score"]
    print(f"  \033[1mBrier score (3-class)\033[0m ........... "
          f"{b:.4f}  \033[2m{_grade(b)}\033[0m" if b is not None else "  Brier .... —")
    if r["baseline_brier"] is not None:
        bl = r["baseline_brier"]
        delta = bl - (b or bl)
        sign = "\033[32m▼" if delta > 0 else "\033[31m▲"
        print(f"  Naif baseline Brier .............. {bl:.4f}  "
              f"{sign} {abs(delta):.4f} model avantajı\033[0m")
    if r["log_loss"] is not None:
        print(f"  Log loss ......................... {r['log_loss']:.4f}")
    if r["ece"] is not None:
        print(f"  ECE (expected calib. error) ...... {r['ece']:.4f}")
    print()
    if r["buckets"]:
        print("  \033[1mEv-galibiyeti kalibrasyon kovaları:\033[0m")
        print("    aralık            tahmin   gerçek   n")
        for bk in r["buckets"]:
            if bk.sample_count == 0:
                continue
            rng = f"{bk.bucket_lower:.1f}-{bk.bucket_upper:.1f}"
            print(f"    {rng:<16s} {bk.avg_predicted_prob:.2f}     "
                  f"{bk.actual_frequency:.2f}     {bk.sample_count}")
    print()
    print("\033[2m  Not: Backtest fixture (demo) verisi üzerindedir; pilotta kulübün\033[0m")
    print("\033[2m  gerçek sezon verisiyle her gece yeniden hesaplanır.\033[0m\n")


def _render_md(r: dict) -> None:
    b = r["brier_score"]
    print("# Kalibrasyon Raporu — engine.predict (Dixon-Coles)\n")
    print(f"> Sızıntısız backtest, **{r['sample_count']} maç** "
          f"(min {r['min_prior']} geçmiş maç eşiği).\n")
    print("| Metrik | Değer | Yorum |")
    print("|---|---|---|")
    print(f"| Brier score (3-class) | **{b:.4f}** | {_grade(b)} |"
          if b is not None else "| Brier | — | yetersiz örnek |")
    if r["baseline_brier"] is not None:
        print(f"| Naif baseline Brier | {r['baseline_brier']:.4f} | "
              f"sabit lig-ort. olasılığı |")
    if r["log_loss"] is not None:
        print(f"| Log loss | {r['log_loss']:.4f} | düşük = iyi |")
    if r["ece"] is not None:
        print(f"| ECE | {r['ece']:.4f} | tahmin↔gerçek sapması |")
    print()
    if r["buckets"]:
        print("## Ev-galibiyeti kalibrasyon kovaları\n")
        print("| Aralık | Ort. tahmin | Gerçek oran | n |")
        print("|---|---|---|---|")
        for bk in r["buckets"]:
            if bk.sample_count == 0:
                continue
            print(f"| {bk.bucket_lower:.1f}–{bk.bucket_upper:.1f} | "
                  f"{bk.avg_predicted_prob:.2f} | {bk.actual_frequency:.2f} | "
                  f"{bk.sample_count} |")
        print()
    print("> Backtest demo fixture verisi üzerindedir; pilotta kulübün gerçek "
          "sezon verisiyle her gece yeniden hesaplanır ve ML-kalibre ρ öğrenilir.")


def main() -> int:
    parser = argparse.ArgumentParser(description="tactic11 kalibrasyon backtest")
    parser.add_argument("--output", choices=["tty", "md"], default="tty")
    parser.add_argument("--min-prior", type=int, default=3,
                        help="Tahmin için min geçmiş maç sayısı (default 3)")
    args = parser.parse_args()
    r = run(min_prior=args.min_prior)
    if args.output == "md":
        _render_md(r)
    else:
        _render_tty(r)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
