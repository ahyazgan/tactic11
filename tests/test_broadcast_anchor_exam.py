"""Kontrol ölçütleri: ön kayıttaki C1-C5 sayısal olarak."""
from __future__ import annotations

import pytest

pytest.importorskip("cv2")

from scripts.broadcast_anchor_exam import evaluate_control  # noqa: E402


def rows(match: str, main_hits: int, main_n: int, other_hits: int, other_n: int, errors: list[float]) -> list[dict]:
    out = [{"match": match, "label": "main", "accepted": i < main_hits,
            "error_m": errors[i] if i < len(errors) and i < main_hits else None} for i in range(main_n)]
    out += [{"match": match, "label": "other", "accepted": i < other_hits, "error_m": None} for i in range(other_n)]
    return out


def test_passes_when_every_criterion_is_met():
    data = rows("a", 40, 100, 1, 40, [1.0] * 10) + rows("b", 30, 100, 1, 40, [1.5] * 10)
    assert evaluate_control(data)["verdict"] == "GEÇTİ"


@pytest.mark.parametrize(("data", "failed"), [
    (rows("a", 50, 100, 1, 40, [1.0] * 10) + rows("b", 10, 100, 1, 40, [1.0] * 10), "C1_main_acceptance"),
    (rows("a", 40, 100, 1, 40, [3.0] * 10) + rows("b", 40, 100, 1, 40, [3.0] * 10), "C2_accuracy"),
    (rows("a", 40, 100, 1, 40, [1.0] * 8 + [9.0] * 2) + rows("b", 40, 100, 1, 40, [1.0] * 10), "C3_wrong_accept_main"),
    (rows("a", 40, 100, 4, 40, [1.0] * 10) + rows("b", 40, 100, 4, 40, [1.0] * 10), "C4_wrong_accept_other"),
    (rows("a", 40, 100, 1, 40, [1.0] * 7) + rows("b", 40, 100, 1, 40, [1.0] * 7), "C5_minimum_sample"),
])
def test_each_criterion_fails_the_exam_alone(data, failed):
    result = evaluate_control(data)
    assert result["verdict"] == "KALDI"
    assert result["checks"][failed] is False
