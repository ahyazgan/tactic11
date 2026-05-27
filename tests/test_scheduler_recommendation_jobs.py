"""Karar agent'ları için scheduler job kayıtları."""

from __future__ import annotations

import pytest

from app.scheduler.registry import get


@pytest.mark.parametrize("job_name", [
    "run_lineup_recommendation",
    "run_tactical_adjustment",
    "run_lineup_for_upcoming",
])
def test_recommendation_jobs_registered(job_name):
    spec = get(job_name)
    assert spec.name == job_name
    assert callable(spec.handler)
    assert spec.description
