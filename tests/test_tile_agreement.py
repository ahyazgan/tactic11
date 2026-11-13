"""Dilim ayarı karşılaştırması: bire bir eşleme, yarıçap, fazlalık ve kare hizalama."""
from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("scipy")

from scripts.soccertrack_v2 import tile_agreement as agreement  # noqa: E402


def _frame(minute, players):
    return {"minute": minute, "players": [{"x": x, "y": y} for x, y in players]}


def test_each_candidate_player_can_satisfy_only_one_reference_player():
    reference = np.array([[50.0, 50.0], [50.5, 50.0]])
    candidate = np.array([[50.2, 50.0]])
    assert sum(agreement.match_frame(reference, candidate)) == 1


def test_radius_is_measured_in_metres_on_the_pitch_not_in_normalised_units():
    reference = np.array([[50.0, 50.0]])
    # x'te 2 birim = 2,1 m (içeride); y'de 5 birim = 3,4 m (dışarıda)
    assert agreement.match_frame(reference, np.array([[52.0, 50.0]])) == [True]
    assert agreement.match_frame(reference, np.array([[50.0, 55.0]])) == [False]
    assert agreement.match_frame(reference, np.empty((0, 2))) == [False]


def test_compare_counts_missed_and_extra_players_and_skips_unaligned_frames():
    reference = [_frame(1.0, [(10, 10), (50, 50), (90, 90)]), _frame(2.0, [(20, 20)]), _frame(9.0, [(1, 1)])]
    candidate = [_frame(1.0, [(10, 10), (50, 50), (70, 20)]), _frame(2.0, [(20, 20)])]
    result = agreement.compare(reference, candidate)
    assert result["frames_compared"] == 2 and result["reference_frames"] == 3
    assert result["reference_players"] == 4 and result["matched"] == 3
    assert result["recall_vs_reference"] == 0.75
    assert result["extra_share"] == 0.25  # adaydaki 4 oyuncudan 1'i referansta yok
    assert result["band_recall"] == {"y_0_33": 1.0, "y_33_67": 1.0, "y_67_100": 0.0}


def test_compare_of_nothing_reports_zero_instead_of_dividing():
    result = agreement.compare([], [])
    assert result["recall_vs_reference"] == 0.0 and result["extra_share"] == 0.0
