"""xG geometric baseline backtest — kalibrasyon + Brier skoru.

Mevcut engine altyapısına tam entegre:
  - `Shot.is_goal` → ground truth
  - `compute_shot_xg_geometric` → tahmin
  - `engine.backtest.backtest()` → mevcut harness (BacktestReport + CalibrationBin)
  - `EngineResult[XGBacktestReport]` → audit trail taşıyan çıktı

Kullanım — iki senaryo:

  1) Veritabanından yükle (production):
     shots = load_shots_from_db(session, season=2018)
     result = run_xg_geometric_backtest(shots)

  2) StatsBomb Open / fixture JSON'dan yükle (standalone):
     shots = load_shots_from_statsbomb("data/events/")
     result = run_xg_geometric_backtest(shots)

Kalibrasyon yorumu:
  Brier score < 0.07  → iyi (futbolda şutların nadir gol olması bunu baskılar)
  ECE < 0.05          → iyi kalibre
  "0.3 dediğinde %30 çıkıyor mu" → CalibrationBin.observed_rate

Engine kuralı: bu modül DB/HTTP bağımlılığı taşımaz.
load_* fonksiyonları helper; onlar caller tarafında çalışır.
"""
from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.audit import AuditRecord, EngineResult
from app.domain import Shot
from app.engine.backtest.compute import BacktestReport, backtest
from app.engine.xg.compute import compute_shot_xg_geometric

ENGINE_NAME = "engine.xg.backtest"
ENGINE_VERSION = "1"

# ──────────────────────────────────────────────────────────────────────────────
# Çıktı tipleri
# ──────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class PatternBreakdown:
    """Pattern başına kalibrasyon özeti."""
    pattern: str
    n_shots: int
    n_goals: int
    observed_rate: float   # gerçek gol oranı
    mean_xg: float         # modelin öngördüğü ortalama
    brier: float           # bu pattern'e özgü Brier skoru
    bias: float            # mean_xg - observed_rate; + → over-estimate


@dataclass(frozen=True)
class XGBacktestReport:
    """Tüm backtest sonuçları."""
    n_shots: int
    n_goals: int
    observed_goal_rate: float
    mean_predicted_xg: float
    brier_score: float                 # global (düşük = iyi; futbolda ~0.07 hedef)
    expected_calibration_error: float  # ECE (düşük = iyi; <0.05 hedef)
    well_calibrated: bool
    calibration_bins: tuple            # BacktestReport.calibration tuple'ı
    pattern_breakdown: tuple[PatternBreakdown, ...]
    season: int | None
    evaluated_at: datetime


# ──────────────────────────────────────────────────────────────────────────────
# Ana backtest fonksiyonu
# ──────────────────────────────────────────────────────────────────────────────

def run_xg_geometric_backtest(
    shots: Iterable[Shot],
    *,
    season: int | None = None,
    n_calibration_bins: int = 10,
) -> EngineResult[XGBacktestReport]:
    """Geometric xG modelini `shots` üzerinde değerlendir.

    Penalty şutları dahil edilmez — 0.76 sabit değer kalibrasyon
    anlamında bilgi taşımaz, sonuçları ezer.

    Args:
        shots: `Shot.is_goal` dolu olan şutlar (training/eval seti).
        season: Sadece metadata — hangi sezonda test ettiğini izlemek için.
        n_calibration_bins: Kalibrasyon grafiği için bin sayısı (default 10).

    Returns:
        EngineResult[XGBacktestReport] — audit trail ile birlikte.
    """
    # Penalty hariç tut (sabit xG = 0.76, kalibrasyonu kirletir)
    shot_list = [s for s in shots if s.pattern != "penalty"]

    if not shot_list:
        raise ValueError(
            "Backtest için en az 1 penalty-dışı şut gerekli. "
            "Şutlarda is_goal=True/False dolu mu?"
        )

    # (predicted_xg, is_goal) çiftleri — mevcut backtest engine formatı
    samples: list[tuple[float, bool]] = []
    for shot in shot_list:
        result = compute_shot_xg_geometric(shot)
        samples.append((result.value.xg, shot.is_goal))

    # Mevcut engine.backtest harness'ı kullan
    bt: BacktestReport = backtest(
        samples,
        decision_threshold=0.5,
        n_bins=n_calibration_bins,
    )

    # ECE (Expected Calibration Error) — ağırlıklı bin ortalaması
    ece = _compute_ece(bt)

    # Pattern breakdown — hangi şut tipi ne kadar sapıyor?
    breakdown = _pattern_breakdown(shot_list)

    # Özet
    n_goals = sum(1 for _, g in samples if g)
    report = XGBacktestReport(
        n_shots=len(shot_list),
        n_goals=n_goals,
        observed_goal_rate=round(n_goals / len(shot_list), 4),
        mean_predicted_xg=bt.mean_predicted,
        brier_score=bt.brier_score,
        expected_calibration_error=round(ece, 4),
        well_calibrated=bt.well_calibrated,
        calibration_bins=bt.calibration,
        pattern_breakdown=breakdown,
        season=season,
        evaluated_at=datetime.now(UTC),
    )

    audit = AuditRecord(
        engine=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        subject_type="xg_model",
        subject_id=0,
        metric="geometric_xg_calibration",
        value={
            "brier_score": report.brier_score,
            "ece": report.expected_calibration_error,
            "well_calibrated": report.well_calibrated,
            "n_shots": report.n_shots,
            "season": season,
        },
        inputs={
            "n_shots": len(shot_list),
            "n_goals": n_goals,
            "excluded": "penalty",
            "n_calibration_bins": n_calibration_bins,
        },
        formula=(
            "brier = mean((xg_pred - is_goal)^2); "
            "ece = Σ(|bin| / N) * |mean_pred - observed_rate| per bin"
        ),
    )
    return EngineResult(value=report, audit=audit)


# ──────────────────────────────────────────────────────────────────────────────
# Yardımcı hesaplamalar
# ──────────────────────────────────────────────────────────────────────────────

def _compute_ece(bt: BacktestReport) -> float:
    """Weighted ECE — bin büyüklüğüyle ağırlıklandırılmış kalibrasyon hatası."""
    if not bt.calibration or bt.n == 0:
        return 0.0
    total = sum(
        b.n * abs(b.mean_predicted - b.observed_rate)
        for b in bt.calibration
    )
    return total / bt.n


def _pattern_breakdown(
    shots: list[Shot],
) -> tuple[PatternBreakdown, ...]:
    """Pattern başına özet — hangi şut tipi en çok sapıyor."""
    from collections import defaultdict
    groups: dict[str, list[Shot]] = defaultdict(list)
    for s in shots:
        groups[s.pattern].append(s)

    result: list[PatternBreakdown] = []
    for pattern, group in sorted(groups.items()):
        xg_vals = [compute_shot_xg_geometric(s).value.xg for s in group]
        goals = [s.is_goal for s in group]
        n = len(group)
        n_goals = sum(goals)
        observed = n_goals / n
        mean_xg = sum(xg_vals) / n
        brier = sum((p - (1.0 if g else 0.0)) ** 2 for p, g in zip(xg_vals, goals)) / n
        result.append(PatternBreakdown(
            pattern=pattern,
            n_shots=n,
            n_goals=n_goals,
            observed_rate=round(observed, 4),
            mean_xg=round(mean_xg, 4),
            brier=round(brier, 4),
            bias=round(mean_xg - observed, 4),
        ))
    return tuple(result)


# ──────────────────────────────────────────────────────────────────────────────
# Veri yükleme — DB ve StatsBomb Open
# ──────────────────────────────────────────────────────────────────────────────

def load_shots_from_db(session, *, season: int | None = None) -> list[Shot]:
    """SQLAlchemy session'dan Shot listesi çek.

    `session` caller verir — engine kuralı bozulmaz, bu fonksiyon
    backtest modülünde değil, API/scheduler katmanında çağrılır.

    Örnek çağrı (app/api veya scheduler'dan):
        from app.db.session import get_db
        from app.engine.xg.backtest import load_shots_from_db

        with get_db() as session:
            shots = load_shots_from_db(session, season=2018)
            result = run_xg_geometric_backtest(shots, season=2018)
    """
    from app.db import models as m  # geç import — engine katmanında çalışmaz

    q = session.query(m.ShotModel)
    if season is not None:
        q = q.filter(m.ShotModel.season == season)

    shots = []
    for row in q.all():
        shots.append(Shot(
            sport=row.sport,
            match_external_id=row.match_external_id,
            player_external_id=row.player_external_id,
            minute=row.minute,
            x=row.x,
            y=row.y,
            body_part=row.body_part,
            pattern=row.pattern,
            is_goal=row.is_goal,
            team_external_id=getattr(row, "team_external_id", None),
        ))
    return shots


def load_shots_from_statsbomb(events_dir: str | Path) -> list[Shot]:
    """StatsBomb Open Data events/*.json'dan Shot listesi yükle.

    StatsBomb koordinat sistemi: x=0-120, y=0-80.
    Bu fonksiyon Shot'un 0-100 normalize sistemine çevirir.

    events_dir içindeki her JSON dosyası bir maçın event listesidir.

    Örnek:
        from app.engine.xg.backtest import load_shots_from_statsbomb
        shots = load_shots_from_statsbomb("data/statsbomb/events/")
        result = run_xg_geometric_backtest(shots, season=2018)
    """
    events_dir = Path(events_dir)
    shots: list[Shot] = []
    FAKE_MATCH_ID_BASE = 900_000  # StatsBomb match_id'leri DB ile çakışmasın

    for json_path in sorted(events_dir.glob("*.json")):
        with open(json_path, encoding="utf-8") as f:
            events = json.load(f)

        if json_path.stem.isdigit():
            match_id = FAKE_MATCH_ID_BASE + int(json_path.stem)
        else:
            match_id = hash(json_path.name) % 10**8

        for ev in events:
            if ev.get("type", {}).get("name") != "Shot":
                continue
            shot_data = ev.get("shot", {})
            loc = ev.get("location", [None, None])
            if len(loc) < 2 or loc[0] is None:
                continue

            # StatsBomb → 0-100 normalize (x: 0-120 → 0-100; y: 0-80 → 0-100)
            x = (loc[0] / 120.0) * 100.0
            y = (loc[1] / 80.0) * 100.0

            # Body part mapping
            bp_raw = shot_data.get("body_part", {}).get("name", "right_foot").lower()
            body_part_map = {
                "head": "head",
                "right foot": "right_foot",
                "left foot": "left_foot",
                "no touch": "other",
            }
            body_part = body_part_map.get(bp_raw, "other")

            # Pattern mapping
            pattern_raw = shot_data.get("type", {}).get("name", "open play").lower()
            if "penalty" in pattern_raw:
                pattern = "penalty"
            elif "free kick" in pattern_raw:
                pattern = "free_kick"
            elif "corner" in pattern_raw:
                pattern = "corner_kick"
            elif "open play" in pattern_raw:
                pattern = "open_play"
            else:
                pattern = "set_piece"

            outcome = shot_data.get("outcome", {}).get("name", "").lower()
            is_goal = outcome == "goal"

            player_id = ev.get("player", {}).get("id", 0)
            minute = float(ev.get("minute", 0))

            try:
                shots.append(Shot(
                    sport="football",
                    match_external_id=match_id,
                    player_external_id=player_id,
                    minute=minute,
                    x=round(x, 2),
                    y=round(y, 2),
                    body_part=body_part,
                    pattern=pattern,
                    is_goal=is_goal,
                ))
            except Exception:
                # Geçersiz koordinat vb. → atla
                continue

    return shots


# ──────────────────────────────────────────────────────────────────────────────
# Raporlama — terminal çıktısı
# ──────────────────────────────────────────────────────────────────────────────

def print_report(result: EngineResult[XGBacktestReport]) -> None:
    """Backtest sonucunu okunabilir formatta yazdır."""
    r = result.value
    print("\n" + "=" * 60)
    print("xG Geometric Baseline — Backtest Raporu")
    if r.season:
        print(f"Sezon: {r.season}")
    print(f"Değerlendirildi: {r.evaluated_at.strftime('%Y-%m-%d %H:%M')} UTC")
    print("=" * 60)

    print(f"\n{'Şut sayısı':<30} {r.n_shots:>8}")
    print(f"{'Gerçek gol sayısı':<30} {r.n_goals:>8}")
    print(f"{'Gerçek gol oranı':<30} {r.observed_goal_rate:>8.3f}")
    print(f"{'Modelin ortalama xG tahmini':<30} {r.mean_predicted_xg:>8.3f}")

    bias = r.mean_predicted_xg - r.observed_goal_rate
    bias_label = "ÜST-TAHMIN" if bias > 0.01 else ("ALT-TAHMIN" if bias < -0.01 else "dengeli")
    print(f"{'Bias (mean_xg - observed)':<30} {bias:>+8.3f}  → {bias_label}")

    print(f"\n{'Brier Score':<30} {r.brier_score:>8.4f}  (hedef < 0.07)")
    print(f"{'ECE':<30} {r.expected_calibration_error:>8.4f}  (hedef < 0.05)")
    calibration_verdict = "✓ İyi kalibre" if r.well_calibrated else "✗ Kalibrasyon zayıf"
    print(f"{'Kalibrasyon':<30} {calibration_verdict:>20}")

    # Kalibrasyon tablosu
    if r.calibration_bins:
        print("\n--- Kalibrasyon Binleri ---")
        print(f"{'Aralık':<14} {'N':>6} {'Tahmin':>10} {'Gözlenen':>10} {'Fark':>8}")
        print("-" * 52)
        for b in r.calibration_bins:
            diff = b.mean_predicted - b.observed_rate
            flag = " ⚠" if abs(diff) > 0.10 else ""
            print(
                f"[{b.lower:.2f}, {b.upper:.2f})  "
                f"{b.n:>6}  "
                f"{b.mean_predicted:>10.3f}  "
                f"{b.observed_rate:>10.3f}  "
                f"{diff:>+8.3f}{flag}"
            )

    # Pattern breakdown
    if r.pattern_breakdown:
        print("\n--- Pattern Başına Analiz ---")
        print(f"{'Pattern':<16} {'N':>6} {'Gol':>5} {'Gözlenen':>10} {'meanXG':>8} {'Bias':>8}")
        print("-" * 58)
        for p in r.pattern_breakdown:
            flag = " ⚠" if abs(p.bias) > 0.05 else ""
            print(
                f"{p.pattern:<16} {p.n_shots:>6} {p.n_goals:>5} "
                f"{p.observed_rate:>10.3f} {p.mean_xg:>8.3f} {p.bias:>+8.3f}{flag}"
            )

    print("\n" + "=" * 60 + "\n")


# ──────────────────────────────────────────────────────────────────────────────
# Standalone çalıştırma — python -m app.engine.xg.backtest
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    events_dir = sys.argv[1] if len(sys.argv) > 1 else "data/statsbomb/events"
    season_arg = int(sys.argv[2]) if len(sys.argv) > 2 else None

    print(f"StatsBomb events yükleniyor: {events_dir}")
    shots = load_shots_from_statsbomb(events_dir)
    print(f"{len(shots)} şut yüklendi (penalty hariç tutulacak).")

    result = run_xg_geometric_backtest(shots, season=season_arg)
    print_report(result)
