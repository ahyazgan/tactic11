"""Momentum sinyalinin YÖNÜ ve DOYGUNLUĞU — ölçümle bulunan iki kusur.

Gerçek veriyle ölçüldü (n=437 karar, Barcelona külliyatı):

1. `abs()` yönü siliyordu. "Momentum bizde" ile "Rakip baskı kuruyor" aynı
   magnitude'ü ve aynı güveni alıyordu, oysa sonuçları taban tabana zıt:
       biz baskın   (n=314): %21 olumlu, %39 olumsuz
       rakip baskın (n= 75): %44 olumlu, %5  olumsuz
   Zıt durumlar zıt tavsiye ister; tek kovaya koymak öğrenmeyi imkânsız kılar.

2. Sert kırpma doygunluk yaratıyordu: kararların %64'ü magnitude 1.00'da
   toplanmıştı ve o grubun olumsuz oranı iki katıydı — ayırt edecek bilgi tam
   da kırpmada yok oluyordu.
"""
from __future__ import annotations

from app.api.context_pipeline import _soft_saturate, build_candidates
from app.engine.context_engine.compute import THEME_BY_TYPE

WIN = {"passes": 40, "defs": 12, "shots": 4}


def _momentum(*, holder: str, score: float, raw: float | None = None) -> dict:
    return {"momentum": {
        "momentum_score": score,
        "momentum_raw": score if raw is None else raw,
        "momentum_holder": holder,
        "press_breaking": False, "xg_swing_alert": False,
        "alert_text": "Momentum bizde" if holder == "us" else "Rakip baskı kuruyor",
    }}


def _sig(out: dict, key: str = "momentum"):
    cands = build_candidates(out, current_minute=66.0, win=WIN)
    return next(c for c in cands if c.key == key)


# --- yön ------------------------------------------------------------------- #

def test_direction_produces_distinct_signal_types() -> None:
    """Zıt durumlar AYRI tip olmalı — yoksa geçmiş isabet ikisini ayıramaz."""
    biz = _sig(_momentum(holder="us", score=0.8))
    rakip = _sig(_momentum(holder="opponent", score=-0.8))
    assert biz.signal_type == "momentum_us"
    assert rakip.signal_type == "momentum_opp"
    assert biz.signal_type != rakip.signal_type


def test_both_directions_keep_the_same_theme() -> None:
    """Tip ayrıldı ama tema aynı: ikisi de şekil ayarı gerektirir.

    Tema eşlemesinde eksik bir tip sessizce KeyError'a ya da yanlış gruplamaya
    yol açardı; kayıt burada kilitlenir.
    """
    assert THEME_BY_TYPE["momentum_us"] == "adjust_shape"
    assert THEME_BY_TYPE["momentum_opp"] == "adjust_shape"


def test_balanced_momentum_stays_generic() -> None:
    """Denge durumunda yön iddiası yok — eski genel tip korunur."""
    s = _sig(_momentum(holder="balanced", score=0.05))
    assert s.signal_type == "tactical"


def test_opposite_directions_no_longer_collapse_to_one_magnitude() -> None:
    """Aynı şiddet, zıt yön → ARTIK ayırt edilebilir.

    Eskiden `abs()` yüzünden ikisi de aynı magnitude'ü alıyordu; magnitude hâlâ
    şiddeti ölçer ama TİP yönü taşıdığı için karar ayrışır.
    """
    biz = _sig(_momentum(holder="us", score=0.9))
    rakip = _sig(_momentum(holder="opponent", score=-0.9))
    assert biz.magnitude == rakip.magnitude          # şiddet aynı
    assert biz.signal_type != rakip.signal_type      # ama karar ayrı


# --- doygunluk ------------------------------------------------------------- #

def test_soft_saturation_keeps_extremes_distinguishable() -> None:
    """ASIL KUSUR: `min(1.0, x)` 1.2 ile 10.0'ı aynı sayıya indiriyordu."""
    az = _soft_saturate(1.2)
    cok = _soft_saturate(10.0)
    assert az < cok, "kırpma hâlâ ayrımı yok ediyor"
    assert 0.0 <= az < 1.0 and 0.0 <= cok < 1.0


def test_soft_saturation_is_monotone_and_bounded() -> None:
    degerler = [_soft_saturate(x) for x in (0.0, 0.25, 0.5, 1.0, 2.0, 5.0, 50.0)]
    assert degerler == sorted(degerler)
    assert degerler[0] == 0.0
    assert all(0.0 <= d < 1.0 for d in degerler)


def test_saturated_raw_momentum_no_longer_flattens() -> None:
    """Kırpılmış skor aynı olsa bile HAM değer farklıysa magnitude farklı olmalı.

    Gerçek veride tam bu oluyordu: `momentum_score` ±1'e kırpılmış geliyor,
    kararların %64'ü tek bir değerde toplanıyordu.
    """
    hafif = _sig(_momentum(holder="us", score=1.0, raw=1.05))
    ezici = _sig(_momentum(holder="us", score=1.0, raw=6.0))
    assert hafif.magnitude < ezici.magnitude


def test_missing_raw_falls_back_to_clipped_score() -> None:
    """Eski kayıtlarda `momentum_raw` yok — hat çökmemeli."""
    out = {"momentum": {
        "momentum_score": 0.7, "momentum_holder": "us",
        "press_breaking": False, "xg_swing_alert": False, "alert_text": "x",
    }}
    s = _sig(out)
    assert 0.0 <= s.magnitude < 1.0
    assert s.signal_type == "momentum_us"
