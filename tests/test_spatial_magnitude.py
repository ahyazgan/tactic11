"""`spatial` sinyalinin magnitude'ü — ölçümle bulunan bir "ölü sabit".

Gerçek veriyle ölçüldü (n=67 karar): `spatial` magnitude'ü **67 kararın
hepsinde 0.600**, standart sapma 0.000. Yani kanıt gücü hakkında SIFIR bilgi
taşıyordu; güven skorunun o payı gürültüydü.

Oysa `spatial_control` raporu gerçek büyüklükleri ZATEN üretiyor
(`our_zone14_passes`, `flank_balance[].diff`, `width_y_std`) — hat onları yok
sayıp sabit yazıyordu.

Artık magnitude = ateşleyen uyarılar arasında **eşiği en çok aşanın** gücü.
"""
from __future__ import annotations

from app.api.context_pipeline import build_candidates
from app.engine.spatial_control.compute import (
    GAP_OUR_MIN,
    NARROW_STD,
    SUPERIORITY_DIFF,
    WIDE_STD,
)

WIN = {"passes": 40, "defs": 12, "shots": 4}


def _out(**alanlar) -> dict:
    temel = {
        "alerts": ("bir uyarı",),
        "gap_between_lines": False, "our_zone14_passes": 0, "opp_zone14_defs": 0,
        "superiority_flank": None, "flank_balance": [],
        "shape_state": "balanced", "width_y_std": 20.0,
    }
    temel.update(alanlar)
    return {"spatial_control": temel}


def _mag(out: dict) -> float:
    c = next(c for c in build_candidates(out, current_minute=66.0, win=WIN)
             if c.key == "spatial_control")
    return c.magnitude


def test_magnitude_is_no_longer_a_constant() -> None:
    """ASIL KUSUR: her durumda 0.600 yazılıyordu."""
    zayif = _mag(_out(gap_between_lines=True, our_zone14_passes=GAP_OUR_MIN))
    guclu = _mag(_out(gap_between_lines=True, our_zone14_passes=GAP_OUR_MIN + 12))
    assert zayif != guclu
    assert guclu > zayif
    assert 0.6 not in {round(zayif, 3), round(guclu, 3)} or zayif != guclu


def test_gap_magnitude_grows_with_zone14_passes() -> None:
    """Eşiği ne kadar çok aşarsa kanıt o kadar güçlü."""
    degerler = [_mag(_out(gap_between_lines=True, our_zone14_passes=GAP_OUR_MIN + k))
                for k in (0, 2, 5, 15)]
    assert degerler == sorted(degerler)
    assert degerler[0] < degerler[-1]


def test_superiority_magnitude_uses_the_flank_difference() -> None:
    """Kanat farkı 2 ile 9 aynı güveni vermemeli."""
    az = _mag(_out(superiority_flank="right",
                   flank_balance=[{"flank": "right", "diff": SUPERIORITY_DIFF}]))
    cok = _mag(_out(superiority_flank="right",
                    flank_balance=[{"flank": "right", "diff": SUPERIORITY_DIFF + 7}]))
    assert cok > az


def test_shape_magnitude_measures_distance_from_threshold() -> None:
    """Darlık/genişlik: eşikten ne kadar saptığı ölçülür."""
    hafif_dar = _mag(_out(shape_state="narrow", width_y_std=NARROW_STD - 1))
    cok_dar = _mag(_out(shape_state="narrow", width_y_std=1.0))
    assert cok_dar > hafif_dar

    hafif_genis = _mag(_out(shape_state="wide", width_y_std=WIDE_STD + 1))
    cok_genis = _mag(_out(shape_state="wide", width_y_std=WIDE_STD + 20))
    assert cok_genis > hafif_genis


def test_strongest_alert_decides() -> None:
    """Birden çok uyarı ateşlerse EN GÜÇLÜSÜ magnitude'ü belirler."""
    tek = _mag(_out(gap_between_lines=True, our_zone14_passes=GAP_OUR_MIN + 1))
    ikili = _mag(_out(
        gap_between_lines=True, our_zone14_passes=GAP_OUR_MIN + 1,
        superiority_flank="left",
        flank_balance=[{"flank": "left", "diff": SUPERIORITY_DIFF + 20}],
    ))
    assert ikili > tek


def test_magnitude_stays_in_range() -> None:
    """Doyum sınırlı: uç değerler bile [0,1) dışına çıkmamalı."""
    m = _mag(_out(gap_between_lines=True, our_zone14_passes=999,
                  superiority_flank="left",
                  flank_balance=[{"flank": "left", "diff": 999}],
                  shape_state="wide", width_y_std=999.0))
    assert 0.0 <= m < 1.0


def test_missing_fields_do_not_crash() -> None:
    """Eski/eksik rapor sözlüğü hattı çökertmemeli."""
    c = build_candidates({"spatial_control": {"alerts": ("x",)}},
                         current_minute=66.0, win=WIN)
    s = next(x for x in c if x.key == "spatial_control")
    assert 0.0 <= s.magnitude < 1.0
