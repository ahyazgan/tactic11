"""Video işçisi bellek kapısı: yetmeyen belleği iş başlamadan söyler, ölçemediğinde uydurmaz."""
from __future__ import annotations

import os

import pytest

from app.core import system_resources as res


def test_enough_memory_passes():
    assert res.worker_memory_error({"avail_phys_mb": 9000, "avail_commit_mb": 11000}, 11000) is None


def test_short_memory_names_both_numbers_and_the_remedy():
    message = res.worker_memory_error({"avail_phys_mb": 4000, "avail_commit_mb": 7500}, 11000)
    assert message is not None
    assert "11 GB" in message and "7.5 GB" in message and "kapatıp" in message


def test_unmeasurable_memory_and_disabled_gate_do_not_refuse():
    assert res.worker_memory_error(None, 11000) is None
    assert res.worker_memory_error({"avail_phys_mb": 1, "avail_commit_mb": 1}, 0) is None


@pytest.mark.parametrize(("raw", "expected"), [(None, res.DEFAULT_MIN_COMMIT_MB), ("0", 0), ("16000", 16000),
                                               ("çok", res.DEFAULT_MIN_COMMIT_MB)])
def test_threshold_comes_from_the_environment_or_the_measured_default(monkeypatch, raw, expected):
    if raw is None:
        monkeypatch.delenv(res.MIN_COMMIT_ENV, raising=False)
    else:
        monkeypatch.setenv(res.MIN_COMMIT_ENV, raw)
    assert res.min_commit_mb() == expected


def test_measurement_is_real_on_windows_and_absent_elsewhere():
    memory = res.system_memory_mb()
    if os.name != "nt":
        assert memory is None
    else:
        assert memory is not None and memory["avail_commit_mb"] > 0 and memory["avail_phys_mb"] > 0
