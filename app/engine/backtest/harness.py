"""Tahmin backtest harness — predict v3 + kalibrasyon T'nin gerçek-veri kazancı.

Walk-forward değerlendirme: her maç için yalnız ÖNCEKİ maçlardan form kurar
(sızıntı yok), baseline (eski saf-atak) ve v3 (rakip-göreli + ev sahibi) modelleri
ile tahmin eder, gerçek sonuca karşı Brier + log-loss + ECE + isabet hesaplar.

Kalibrasyon: v3 tahminlerini train/test böl, train'de sıcaklık T öğren, test'te
ham vs kalibre log-loss karşılaştır.

Saf-ish: girdi maç satırı listesi → karşılaştırma raporu. (compute_form/
compute_predict/compute_calibration motorlarını kullanır; DB/HTTP yok.)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.domain import Match
from app.engine.calibration import compute_calibration, fit_temperature
from app.engine.form import compute_form
from app.engine.predict import compute_predict
from app.sports import football


@dataclass(frozen=True)
class MatchRow:
    date: str  # "YYYY-MM-DD"
    home: str
    away: str
    hg: int
    ag: int


@dataclass(frozen=True)
class ModelMetrics:
    label: str
    n: int
    brier: float
    log_loss: float
    ece: float
    accuracy: float


@dataclass(frozen=True)
class CalibrationDelta:
    n_test: int
    temperature: float
    log_loss_raw: float
    log_loss_calibrated: float


@dataclass(frozen=True)
class BacktestComparison:
    baseline: ModelMetrics
    v3: ModelMetrics
    calibration: CalibrationDelta | None


def _outcome(hg: int, ag: int) -> str:
    return "home" if hg > ag else ("draw" if hg == ag else "away")


def _to_match(ext_id: int, hid: int, aid: int, hg: int, ag: int, kickoff: datetime) -> Match:
    return Match(
        sport=football.SPORT_NAME, external_id=ext_id,
        league_external_id=1, season=2024, kickoff=kickoff, status="FT",
        home_team_external_id=hid, away_team_external_id=aid,
        home_score=hg, away_score=ag,
    )


def _accuracy(samples: list[tuple[float, float, float, str]]) -> float:
    if not samples:
        return 0.0
    hits = 0
    for ph, pd, pa, actual in samples:
        pred = max((("home", ph), ("draw", pd), ("away", pa)), key=lambda x: x[1])[0]
        if pred == actual:
            hits += 1
    return round(hits / len(samples), 4)


def _metrics(label: str, samples: list[tuple[float, float, float, str]]) -> ModelMetrics:
    rep = compute_calibration(samples, recalibrate=False).value
    return ModelMetrics(
        label=label, n=rep.sample_count,
        brier=rep.brier_score or 0.0,
        log_loss=rep.log_loss or 0.0,
        ece=rep.expected_calibration_error or 0.0,
        accuracy=_accuracy(samples),
    )


def run_backtest(
    rows: list[MatchRow],
    *,
    last_n: int = 8,
    warmup: int = 4,
    train_frac: float = 0.5,
) -> BacktestComparison:
    """Walk-forward backtest. `warmup`: bir takımın tahmin edilebilmesi için
    gereken min önceki maç. `train_frac`: kalibrasyon train/test bölme oranı.
    """
    # Takım adı → kararlı int id.
    ids: dict[str, int] = {}

    def _id(name: str) -> int:
        return ids.setdefault(name, len(ids) + 1)

    # Tarihe göre sırala; her takımın geçmiş maçlarını biriktir.
    ordered = sorted(rows, key=lambda r: r.date)
    history: dict[int, list[Match]] = {}
    base_t = datetime(2024, 1, 1, tzinfo=UTC)

    baseline_samples: list[tuple[float, float, float, str]] = []
    v3_samples: list[tuple[float, float, float, str]] = []

    for i, r in enumerate(ordered):
        hid, aid = _id(r.home), _id(r.away)
        h_hist = history.get(hid, [])
        a_hist = history.get(aid, [])

        if len(h_hist) >= warmup and len(a_hist) >= warmup:
            home_form = compute_form(hid, h_hist, last_n=last_n).value
            away_form = compute_form(aid, a_hist, last_n=last_n).value
            actual = _outcome(r.hg, r.ag)

            base = compute_predict(
                home_form, away_form, home_team_id=hid, away_team_id=aid,
                opponent_weight=0.0, home_advantage=1.0,
            ).value
            v3 = compute_predict(
                home_form, away_form, home_team_id=hid, away_team_id=aid,
            ).value
            baseline_samples.append(
                (base.prob_home_win, base.prob_draw, base.prob_away_win, actual)
            )
            v3_samples.append(
                (v3.prob_home_win, v3.prob_draw, v3.prob_away_win, actual)
            )

        # Bu maçı her iki takımın geçmişine ekle (tahminden SONRA → sızıntı yok).
        kickoff = base_t + timedelta(days=i)
        m = _to_match(i + 1, hid, aid, r.hg, r.ag, kickoff)
        history.setdefault(hid, []).append(m)
        history.setdefault(aid, []).append(m)

    baseline = _metrics("baseline (saf-atak, w=0 hfa=1)", baseline_samples)
    v3 = _metrics("v3 (rakip-göreli + ev sahibi)", v3_samples)

    calibration: CalibrationDelta | None = None
    split = int(len(v3_samples) * train_frac)
    train, test = v3_samples[:split], v3_samples[split:]
    if len(train) >= 20 and test:
        calib = fit_temperature(train)
        from app.engine.calibration import apply_temperature
        raw_ll = compute_calibration(test, recalibrate=False).value.log_loss or 0.0
        cal_test = [
            (*apply_temperature((ph, pd, pa), calib.temperature), actual)
            for ph, pd, pa, actual in test
        ]
        cal_ll = compute_calibration(cal_test, recalibrate=False).value.log_loss or 0.0
        calibration = CalibrationDelta(
            n_test=len(test), temperature=calib.temperature,
            log_loss_raw=raw_ll, log_loss_calibrated=cal_ll,
        )

    return BacktestComparison(baseline=baseline, v3=v3, calibration=calibration)
