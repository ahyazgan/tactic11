"""Morning brief scheduler job testleri (Faz 5 #18)."""
from __future__ import annotations

from unittest.mock import patch

import pytest

# Job spec registry side-effect import
from app.scheduler import jobs as jobs_module  # noqa: F401
from app.scheduler.registry import resolve


def test_morning_brief_registered() -> None:
    """JobSpec 'morning_brief' kayıtlı + resolve edilebiliyor."""
    spec = resolve("morning_brief")
    assert spec is not None
    assert spec.name == "morning_brief"
    assert "sabah" in spec.description.lower() or "morning" in spec.description.lower()
    assert callable(spec.handler)


def test_morning_brief_delegates_to_pre_match_reports() -> None:
    """morning_brief_handler horizon_days=1 ile run_pre_match_reports_handler'ı çağırır."""
    from app.scheduler.jobs import morning_brief_handler

    with patch(
        "app.scheduler.jobs.run_pre_match_reports_handler"
    ) as mock_run:
        morning_brief_handler()
        mock_run.assert_called_once_with(horizon_days=1)


def test_morning_brief_horizon_can_be_overridden() -> None:
    """horizon_days kwarg ile override edilebilir (hafta sonu öncesi 2-3 gün)."""
    from app.scheduler.jobs import morning_brief_handler

    with patch(
        "app.scheduler.jobs.run_pre_match_reports_handler"
    ) as mock_run:
        morning_brief_handler(horizon_days=3)
        mock_run.assert_called_once_with(horizon_days=3)


def test_morning_brief_in_deployment_docs() -> None:
    """DEPLOYMENT.md'de morning_brief crontab girdisi olmalı."""
    from pathlib import Path
    docs = Path(__file__).resolve().parent.parent / "DEPLOYMENT.md"
    if not docs.exists():
        pytest.skip("DEPLOYMENT.md repo'da yok")
    content = docs.read_text(encoding="utf-8")
    assert "morning_brief" in content
    # Crontab girdisi: cron expression + run_job.py morning_brief
    assert "run_job.py morning_brief" in content


def test_run_pre_match_reports_still_registered() -> None:
    """Mevcut run_pre_match_reports job'u bozulmadı."""
    spec = resolve("run_pre_match_reports")
    assert spec is not None
    assert callable(spec.handler)
