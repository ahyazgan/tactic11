"""Protokol kütüphanesi (performance_test) ↔ norm seti (load_risk) tutarlılığı.

Tablet veri girişi (battery, PROTOCOLS.norm_cutoffs) ile risk/trend (REFERENCE)
aynı protokolü aynı anahtar/birim/yön ile tanımalı. Aksi halde girilen test
risk motorunda eşleşmez (latent veri kopukluğu)."""

from app.engine.performance_test import PROTOCOLS
from app.engine.physical.load_risk import REFERENCE


def test_every_protocol_has_norm():
    for key in PROTOCOLS:
        assert key in REFERENCE, f"{key} protokol kütüphanesinde var ama normu yok"


def test_units_match():
    for key, proto in PROTOCOLS.items():
        assert proto.unit == REFERENCE[key]["unit"], (
            f"{key} birim uyumsuz: lib={proto.unit} norm={REFERENCE[key]['unit']}"
        )


def test_direction_matches():
    # higher_is_better (lib) ile lower_is_better (norm) zıt olmalı.
    for key, proto in PROTOCOLS.items():
        assert proto.higher_is_better != REFERENCE[key]["lower_is_better"], (
            f"{key} yön uyumsuz"
        )
